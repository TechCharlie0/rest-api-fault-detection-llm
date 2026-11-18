"""Pipeline orchestrator and condition runner."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agenticapi.agents.base import AgentContext
from agenticapi.agents.code_renderer import write_case
from agenticapi.agents.generator import GeneratorAgent, LLMGenerationError
from agenticapi.agents.oracle import OracleAgent
from agenticapi.agents.planner import PlannerAgent
from agenticapi.agents.repairer import RepairerAgent
from agenticapi.agents.spec_analyst import SpecAnalystAgent
from agenticapi.agents.validator import ValidatorAgent
from agenticapi.config import Settings
from agenticapi.evaluation.baselines import legacy_cases
from agenticapi.evaluation.conditions import ConditionSpec
from agenticapi.evaluation.fault_runner import run_fault_suite
from agenticapi.evaluation.faults import applicable_fault_ids
from agenticapi.evaluation.metrics import coverage_metrics, summarize
from agenticapi.execution.executor import ExecutionEngine
from agenticapi.llm.gateway import LLMGateway
from agenticapi.llm.provider import DeterministicProvider, LLMProvider, build_provider
from agenticapi.models import (
    APISpec,
    ConditionResult,
    ConditionStatus,
    DependencyGraph,
    ExecutionResult,
    ExperimentConfig,
    TestCase,
    write_json,
)


class Orchestrator:
    def __init__(
        self,
        settings: Settings,
        spec: APISpec,
        graph: DependencyGraph,
        server: Any,
        run_dir: Path,
        *,
        provider: LLMProvider | None = None,
    ) -> None:
        self.settings = settings
        self.spec = spec
        self.graph = graph
        self.server = server
        self.run_dir = run_dir
        self.provider = provider

    def run_condition(self, condition: ConditionSpec, seed: int = 1) -> ConditionResult:
        started = time.perf_counter()
        condition_dir = self.run_dir / condition.condition_id / f"seed-{seed}"
        condition_dir.mkdir(parents=True, exist_ok=True)
        config = ExperimentConfig(
            name=condition.condition_id,
            condition_id=condition.condition_id,
            spec_path=self.spec.source_path,
            conditions=[condition.condition_id],
            seeds=[seed],
            fault_ids=applicable_fault_ids(self.spec.operations),
            output_dir=str(self.run_dir),
            allow_llm_fallback=condition.allow_fallback,
            llm_timeout_seconds=int(self.settings.llm_timeout_seconds),
            llm_provider=self.settings.llm_provider,
            llm_model=self.settings.llm_model,
        )
        provider = self.provider
        if provider is None:
            provider = (
                build_provider(self.settings, seed=seed)
                if condition.use_llm
                else DeterministicProvider()
            )
        gateway = LLMGateway(provider, self.settings, max_calls=config.max_llm_calls)
        context = AgentContext(
            settings=self.settings,
            spec=self.spec,
            graph=self.graph,
            config=config,
            artifact_dir=condition_dir,
            gateway=gateway,
            use_llm=condition.use_llm,
            allow_fallback=condition.allow_fallback,
        )
        context.extra["seed"] = seed
        context.extra["randomize"] = condition.randomized
        context.extra["llm_roles"] = _llm_roles(condition)
        result = ConditionResult(
            condition=condition.condition_id,
            seed=seed,
            status=ConditionStatus.COMPLETED,
            provider=gateway.provider.name,
            is_llm=gateway.is_llm,
            artifact_dir=str(condition_dir),
        )
        repair_metrics = {
            "attempted": 0,
            "llm_repaired": 0,
            "llm_rejected": 0,
            "fallback_repaired": 0,
            "rejected": 0,
            "post_repair_valid": 0,
        }
        try:
            if condition.use_llm and not gateway.available:
                result.status = ConditionStatus.BLOCKED
                result.errors.append(
                    "LLM condition blocked: configured provider is unavailable. "
                    "For local Ollama set AGENTICAPI_LLM_PROVIDER=ollama and "
                    "AGENTICAPI_LLM_MODEL; for OpenAI-compatible endpoints set "
                    "AGENTICAPI_LLM_API_KEY. Deterministic conditions remain available."
                )
                return self._finish(result, started, condition, context)
            analysis = SpecAnalystAgent().run(context)
            write_json(condition_dir / "analysis.json", analysis)
            plan = (
                PlannerAgent().run(context, analysis)
                if condition.use_planner
                else PlannerAgent.default_plan(context)
            )
            write_json(condition_dir / "plan.json", plan)
            cases = legacy_cases(context) if condition.legacy else GeneratorAgent().run(context, plan, analysis)
            write_json(condition_dir / "cases_raw.json", cases)
            validation = ValidatorAgent().run(context, cases)
            write_json(condition_dir / "validation.json", validation)
            result.cases_generated = len(cases)
            result.cases_valid = validation.valid_count
            executable: list[TestCase] = validation.valid if condition.use_validator else list(cases)
            if condition.use_repair and validation.invalid:
                repair = RepairerAgent().run(context, validation)
                write_json(
                    condition_dir / "repair.json",
                    {
                        "attempted": len(validation.invalid),
                        "repaired": repair.repaired,
                        "dropped": repair.dropped,
                        "generated_by": repair.generated_by,
                        "llm_repaired": repair.llm_repaired,
                        "llm_rejected": repair.llm_rejected,
                        "fallback_repaired": repair.fallback_repaired,
                        "rejected": repair.rejected,
                        "outcomes": repair.outcomes,
                        "notes": repair.notes,
                    },
                )
                executable = list(repair.cases)
                result.cases_valid = len(executable)
                repair_metrics = {
                    "attempted": len(validation.invalid),
                    "llm_repaired": repair.llm_repaired,
                    "llm_rejected": repair.llm_rejected,
                    "fallback_repaired": repair.fallback_repaired,
                    "rejected": repair.rejected,
                    "post_repair_valid": len(repair.cases),
                }
            # No execution-feedback loop is implemented in this pipeline; this
            # flag must never claim otherwise.
            result.execution_feedback_applied = False
            write_json(condition_dir / "cases_executable.json", executable)
            generated_tests = [
                write_case(case, condition_dir / "generated_tests") for case in executable
            ]
            write_json(
                condition_dir / "generated_tests.json",
                [
                    {
                        "case_id": item.case_id,
                        "file_path": item.file_path,
                        "valid": item.valid,
                        "errors": item.errors,
                    }
                    for item in generated_tests
                ],
            )
            invalid_code = [item for item in generated_tests if not item.valid]
            if invalid_code:
                result.errors.append(
                    f"{len(invalid_code)} generated test file(s) failed the code policy"
                )
                executable = [
                    case
                    for case, item in zip(executable, generated_tests, strict=False)
                    if item.valid
                ]
            engine = ExecutionEngine(self.server.base_url)
            oracle = OracleAgent()
            clean_results = []
            clean_execution: list[dict[str, Any]] = []
            clean_records_by_id: dict[str, dict[str, Any]] = {}
            for case in executable:
                record = engine.execute(case)
                outcome = oracle.evaluate(context, case, record, mode=condition.oracle_mode)
                clean_results.append(outcome)
                record_dict = record.to_dict()
                clean_records_by_id[case.case_id] = record_dict
                clean_execution.append(
                    {
                        "case": case.to_dict(),
                        "record": record_dict,
                        "oracle": outcome.to_dict(),
                    }
                )
                result.execution_results.append(
                    ExecutionResult(
                        case_id=case.case_id,
                        status=outcome.outcome.value,
                        duration_ms=sum(step.duration_ms for step in record.steps),
                        error="; ".join(outcome.messages[:2]),
                    )
                )
            result.cases_executed = len(clean_results)
            result.oracle_results = clean_results
            write_json(condition_dir / "clean_results.json", clean_results)
            write_json(condition_dir / "clean_execution.json", clean_execution)
            fault_records: dict[str, list[dict[str, Any]]] = {}
            fault_results = (
                run_fault_suite(
                    context,
                    engine,
                    oracle,
                    executable,
                    fault_ids=config.fault_ids,
                    oracle_mode=condition.oracle_mode,
                    all_cases=True,
                    records=fault_records,
                )
                if condition.use_faults
                else {}
            )
            result.fault_results = fault_results
            write_json(condition_dir / "fault_results.json", fault_results)
            write_json(condition_dir / "fault_execution.json", fault_records)
            result.metrics = summarize(
                clean_results,
                fault_results,
                eligible_fault_ids=config.fault_ids,
                cases=executable,
                clean_records=clean_records_by_id,
                fault_records=fault_records,
            )
            result.metrics["coverage"] = coverage_metrics(
                executable,
                operations_total=len(self.spec.operations),
            )
            result.metrics["repair"] = repair_metrics
            result.metrics["execution_feedback_requested"] = condition.use_execution_feedback
            result.metrics["validation"] = validation.to_dict()
            result.metrics["conditions"] = condition.__dict__
            result.llm_calls = gateway.calls
            result.prompt_tokens = gateway.prompt_tokens
            result.completion_tokens = gateway.completion_tokens
            result.cost_usd = gateway.cost_usd
            if not result.cases_executed:
                result.status = ConditionStatus.FAILED
                result.errors.append("condition produced zero executable cases")
        except LLMGenerationError as exc:
            result.status = ConditionStatus.BLOCKED
            result.errors.append(f"LLM generation blocked: {exc}")
        except Exception as exc:  # noqa: BLE001
            result.status = ConditionStatus.FAILED
            result.errors.append(f"{type(exc).__name__}: {exc}")
        return self._finish(result, started, condition, context)

    def _finish(
        self,
        result: ConditionResult,
        started: float,
        condition: ConditionSpec,
        context: AgentContext,
    ) -> ConditionResult:
        result.duration_seconds = time.perf_counter() - started
        result.llm_calls = context.gateway.calls
        result.prompt_tokens = context.gateway.prompt_tokens
        result.completion_tokens = context.gateway.completion_tokens
        result.cost_usd = context.gateway.cost_usd
        result.metrics.setdefault("condition", condition.condition_id)
        result.metrics.setdefault("description", condition.description)
        result.metrics.setdefault("duration_seconds", result.duration_seconds)
        result.metrics.setdefault("llm_calls", result.llm_calls)
        write_json(Path(result.artifact_dir) / "condition_result.json", result)
        write_json(Path(result.artifact_dir) / "traces.json", context.traces)
        return result


def _llm_roles(condition: ConditionSpec) -> set[str] | None:
    if not condition.use_llm:
        return set()
    if condition.condition_id == "C2_single_llm":
        return {"generation"}
    return {"analysis", "planning", "generation", "repair"}


def new_run_dir(settings: Settings, label: str = "") -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    suffix = f"-{label}" if label else ""
    return settings.artifacts_dir / "runs" / f"{stamp}{suffix}"
