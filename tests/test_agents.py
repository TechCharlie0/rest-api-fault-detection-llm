"""Generator, validator, oracle, repair, and LLM-agent integration tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from agenticapi.agents.base import AgentContext
from agenticapi.agents.code_renderer import render_case, write_case
from agenticapi.agents.generator import GeneratorAgent, LLMGenerationError
from agenticapi.agents.oracle import OracleAgent
from agenticapi.agents.planner import PlannerAgent
from agenticapi.agents.repairer import RepairerAgent
from agenticapi.agents.spec_analyst import SpecAnalystAgent
from agenticapi.agents.validator import ValidatorAgent
from agenticapi.execution.executor import ExecutionEngine
from agenticapi.llm.gateway import LLMGateway
from agenticapi.llm.provider import LLMProvider
from agenticapi.models import (
    Assertion,
    LLMResponse,
    RequestStep,
    Technique,
    TestCase,
)
from agenticapi.security import validate_generated_code


class FakeLLMProvider(LLMProvider):
    name = "fake"
    is_llm = True

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.received: list[dict[str, Any]] = []

    @property
    def configured(self) -> bool:
        return True

    @property
    def model(self) -> str:
        return "fake-model"

    def complete(self, messages, *, response_schema=None, task="", timeout=None) -> LLMResponse:
        self.received.append({"task": task, "messages": list(messages)})
        text = json.dumps(self.payload)
        return LLMResponse(
            provider=self.name,
            model=self.model,
            text=text,
            parsed=self.payload,
            prompt_tokens=10,
            completion_tokens=5,
            is_llm=True,
        )


def make_llm_context(context: AgentContext, payload: dict[str, Any]) -> AgentContext:
    context.use_llm = True
    context.extra["llm_roles"] = {"generation"}
    context.gateway = LLMGateway(FakeLLMProvider(payload))
    return context


def make_repair_context(context: AgentContext, payload: dict[str, Any]) -> AgentContext:
    context.use_llm = True
    context.extra["llm_roles"] = {"repair"}
    context.gateway = LLMGateway(FakeLLMProvider(payload))
    return context


def test_deterministic_pipeline_and_validation(context):
    analysis = SpecAnalystAgent().run(context)
    plan = PlannerAgent().run(context, analysis)
    cases = GeneratorAgent().run(context, plan, analysis)
    assert len(cases) >= 45
    report = ValidatorAgent().run(context, cases)
    assert report.invalid_count == 0
    assert report.valid_count == len(cases)


def test_validator_rejects_undocumented_path(context):
    case = TestCase(
        case_id="bad",
        operation_id="health",
        technique=Technique.FUNCTIONAL,
        steps=[RequestStep(method="GET", path="/not-real", expected_status=200)],
        expected_status=200,
    )
    report = ValidatorAgent().run(context, [case])
    assert report.valid_count == 0
    assert "not documented" in report.invalid[0][1][0]


def test_generated_code_is_policy_clean(context):
    analysis = SpecAnalystAgent().run(context)
    plan = PlannerAgent().run(context, analysis)
    case = GeneratorAgent().run(context, plan, analysis)[0]
    code = render_case(case)
    assert validate_generated_code(code) == []
    generated = write_case(case, context.artifact_dir / "tests")
    assert generated.valid
    assert Path(generated.file_path).is_file()


def test_llm_generation_path(context):
    payload = {
        "cases": [
            {
                "case_id": "llm_health",
                "operation_id": "health",
                "technique": "functional",
                "description": "LLM health check",
                "steps": [
                    {
                        "method": "GET",
                        "path": "/health",
                        "expected_status": 200,
                    }
                ],
                "assertions": [{"kind": "status", "expected": 200}],
                "expected_status": 200,
            }
        ]
    }
    llm_context = make_llm_context(context, payload)
    plan = PlannerAgent.default_plan(llm_context)
    cases = GeneratorAgent().run(llm_context, plan)
    assert len(cases) == 1
    assert cases[0].generated_by == "llm"
    assert cases[0].case_id == "llm_health"
    assert llm_context.gateway.calls == 1


def test_llm_generation_failure_without_fallback(context):
    class BrokenProvider(FakeLLMProvider):
        def complete(self, messages, *, response_schema=None, task="", timeout=None):
            return LLMResponse(provider="fake", model="fake", error="boom", is_llm=True)

    context.use_llm = True
    context.extra["llm_roles"] = {"generation"}
    context.gateway = LLMGateway(BrokenProvider({}))
    with pytest.raises(LLMGenerationError):
        GeneratorAgent().run(context, PlannerAgent.default_plan(context))


def test_deterministic_repair_sets_expected_status(context):
    case = TestCase(
        case_id="repair_me",
        operation_id="health",
        technique=Technique.FUNCTIONAL,
        steps=[RequestStep(method="GET", path="/health")],
        assertions=[Assertion(kind="status")],
    )
    report = ValidatorAgent().run(context, [case])
    assert report.invalid_count == 1
    repaired = RepairerAgent().run(context, report)
    assert repaired.repaired == 1
    assert repaired.cases[0].expected_status == 200


def _missing_status_case() -> TestCase:
    return TestCase(
        case_id="repair_me",
        operation_id="health",
        technique=Technique.FUNCTIONAL,
        steps=[RequestStep(method="GET", path="/health")],
        assertions=[Assertion(kind="status")],
    )


def _invalid_missing_status_report(context: AgentContext):
    report = ValidatorAgent().run(context, [_missing_status_case()])
    assert report.invalid_count == 1
    return report


def test_llm_repair_accepts_complete_repaired_case(context):
    report = _invalid_missing_status_report(context)
    payload = {
        "cases": [
            {
                "case_id": "repair_me",
                "operation_id": "health",
                "technique": "functional",
                "description": "",
                "steps": [
                    {"method": "GET", "path": "/health", "expected_status": 200}
                ],
                "assertions": [{"kind": "status"}],
                "expected_status": 200,
            }
        ]
    }
    llm_context = make_repair_context(context, payload)
    repaired = RepairerAgent().run(llm_context, report)
    assert repaired.llm_repaired == 1
    assert repaired.llm_rejected == 0
    assert repaired.fallback_repaired == 0
    assert repaired.rejected == 0
    assert repaired.cases[0].expected_status == 200
    assert repaired.generated_by == "llm:fake"
    assert any(outcome["source"] == "llm" for outcome in repaired.outcomes)
    assert llm_context.gateway.calls == 1


def test_llm_repair_rejects_incomplete_output_and_records_fallback(context):
    report = _invalid_missing_status_report(context)
    payload = {
        "cases": [
            {
                "case_id": "repair_me",
                "operation_id": "health",
                "technique": "functional",
            }
        ]
    }
    llm_context = make_repair_context(context, payload)
    repaired = RepairerAgent().run(llm_context, report)
    assert repaired.llm_repaired == 0
    assert repaired.llm_rejected == 1
    assert repaired.fallback_repaired == 1
    assert repaired.rejected == 0
    assert repaired.cases[0].expected_status == 200
    assert any(
        outcome["source"] == "deterministic_fallback" for outcome in repaired.outcomes
    )
    assert llm_context.gateway.calls == 3


def test_llm_repair_rejects_weakened_assertions_and_status(context):
    report = _invalid_missing_status_report(context)
    payload = {
        "cases": [
            {
                "case_id": "repair_me",
                "operation_id": "health",
                "technique": "functional",
                "steps": [{"method": "GET", "path": "/health"}],
                "assertions": [{"kind": "json_path", "target": "status"}],
                "expected_status": 500,
            }
        ]
    }
    llm_context = make_repair_context(context, payload)
    repaired = RepairerAgent().run(llm_context, report)
    assert repaired.llm_repaired == 0
    assert repaired.llm_rejected == 1
    assert repaired.fallback_repaired == 1
    notes = " ".join(outcome["note"] for outcome in repaired.outcomes)
    assert "weakened assertion" in notes
    assert "does not match documented success status" in notes


def test_llm_repair_rejects_objective_change(context):
    report = _invalid_missing_status_report(context)
    payload = {
        "cases": [
            {
                "case_id": "repair_me",
                "operation_id": "list_products",
                "technique": "functional",
                "steps": [
                    {"method": "GET", "path": "/products", "expected_status": 200}
                ],
                "assertions": [{"kind": "status"}],
                "expected_status": 200,
            }
        ]
    }
    llm_context = make_repair_context(context, payload)
    repaired = RepairerAgent().run(llm_context, report)
    assert repaired.llm_repaired == 0
    assert repaired.llm_rejected == 1
    assert repaired.fallback_repaired == 1
    notes = " ".join(outcome["note"] for outcome in repaired.outcomes)
    assert "operation_id changed" in notes


def test_repair_rejection_preserves_original_case(context):
    case = TestCase(
        case_id="repair_me",
        operation_id="health",
        technique=Technique.FUNCTIONAL,
        steps=[RequestStep(method="GET", path="/not-documented")],
        assertions=[Assertion(kind="status")],
    )
    report = ValidatorAgent().run(context, [case])
    assert report.invalid_count == 1
    payload = {
        "cases": [
            {
                "case_id": "repair_me",
                "operation_id": "health",
                "technique": "functional",
            }
        ]
    }
    llm_context = make_repair_context(context, payload)
    repaired = RepairerAgent().run(llm_context, report)
    assert repaired.llm_repaired == 0
    assert repaired.fallback_repaired == 0
    assert repaired.rejected == 1
    assert repaired.rejected_cases[0].case_id == "repair_me"
    assert repaired.rejected_cases[0].steps[0].path == "/not-documented"
    assert any(outcome["source"] == "rejected" for outcome in repaired.outcomes)


def test_oracle_detects_injected_status_fault(context, live_server):
    analysis = SpecAnalystAgent().run(context)
    plan = PlannerAgent().run(context, analysis)
    cases = GeneratorAgent().run(context, plan, analysis)
    case = next(case for case in cases if case.case_id == "get_product__functional")
    engine = ExecutionEngine(live_server.base_url)
    engine.set_fault("F01")
    record = engine.execute(case)
    result = OracleAgent().evaluate(context, case, record)
    engine.set_fault(None)
    assert result.outcome.value == "FAIL"
    assert result.failure_kind == "status"
