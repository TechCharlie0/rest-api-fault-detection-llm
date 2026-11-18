from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agenticapi.execution.executor import ExecutionEngine
from agenticapi.llm.gateway import LLMGateway
from agenticapi.llm.provider import OllamaProvider
from agenticapi.mock_api.server import MockAPIServer
from agenticapi.models import Technique
from agenticapi.spec.loader import load_spec


@dataclass
class AgentStep:
    """Records one agent's execution in the multi-agent pipeline."""
    agent_name: str
    start_time: float
    end_time: float | None = None
    input_data: dict[str, Any] | None = None
    output_data: dict[str, Any] | None = None
    status: str = "running"
    error: str | None = None
    duration_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MultiAgentRun:
    """Complete recording of a multi-agent pipeline execution."""
    run_id: str
    dataset_path: str
    dataset_hash: str
    model_name: str
    ollama_version: str = "0.40.16"
    spec_version: str = ""
    agent_steps: list[AgentStep] = field(default_factory=list)
    total_duration_ms: float = 0.0
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def compute_dataset_hash(path: str | Path) -> str:
    """Compute SHA-256 hash of a dataset file for reproducibility."""
    data = Path(path).read_bytes()
    return hashlib.sha256(data).hexdigest()[:16]


def new_run_id() -> str:
    """Generate a unique run identifier."""
    timestamp = int(time.time())
    hash_part = hashlib.sha256(str(time.time()).encode()).hexdigest()[:8]
    return f"multi_agent_{timestamp}_{hash_part}"


class PlannerAgent:
    """Analyzes the OpenAPI specification and produces a test plan."""
    name = "planner"

    def run(self, context, analysis=None):
        items = []
        for op in context.spec.operations:
            techniques = [Technique.FUNCTIONAL]
            if op.query_parameters or op.path_parameters or op.request_body:
                techniques.append(Technique.NEGATIVE)
            if op.query_parameters or op.path_parameters or op.request_body:
                techniques.append(Technique.BOUNDARY)
            if op.requires_auth:
                techniques.append(Technique.AUTH)
            if getattr(op, "extensions", {}).get("x-agenticapi-authz"):
                techniques.append(Technique.AUTHZ)

            item = type("obj", (), {
                "operation_id": op.operation_id,
                "techniques": techniques,
                "priority": analysis.risk_by_operation.get(op.operation_id, 0)
                if hasattr(analysis, "risk_by_operation") else 0,
                "max_cases": 8,
                "rationale": f"Generate test cases for {op.method} {op.path}",
            })
            items.append(item)

        return type("obj", (), {"items": items})()


class GeneratorAgent:
    """Uses the Ollama LLM to generate structured test cases."""

    name = "generator"

    def __init__(self, *, model: str = "qwen2.5:1.5b", base_url: str = "http://localhost:11434",
                 timeout: float = 30.0, max_calls: int = 60, max_repairs: int = 2):
        self.model = model
        self.base_url = base_url
        self.timeout = timeout
        self.llm_provider = OllamaProvider(model=model, base_url=base_url, timeout=timeout)
        self.llm_gateway = LLMGateway(
            provider=self.llm_provider,
            max_calls=max_calls,
            max_repairs=max_repairs,
        )

    def run(self, context, plan):
        generated: list[Any] = []

        try:
            from agenticapi.llm.prompts import SYSTEM_PROMPT

            operations_context = ""
            for item in plan.items:
                op = context.spec.operation(item.operation_id)
                operations_context += f"- {op.method} {op.path} ({op.operation_id})" + "\n"

            user_prompt = (
                "Generate exactly one JSON object with these fields:" + "\n"
                "- case_id: string" + "\n"
                "- operation_id: string" + "\n"
                "- technique: string (functional/boundary/negative/auth/authz/stateful)" + "\n"
                "- description: string" + "\n"
                "- steps: array of objects with method (string) and path (string)" + "\n"
                "- assertions: array of objects with kind (string) and expected (any)" + "\n"
                "- expected_status: integer or null" + "\n\n"
                "No prose, no markdown fences, no code blocks. Return only the JSON object."
            )

            full_prompt = user_prompt + "\n\nOperations:\n" + operations_context
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": full_prompt},
            ]

            response = self.llm_gateway.complete(
                task="generate_test_cases",
                messages=messages,
            )

            generated = []
            if response.text and not response.error:
                clean_text = re.sub(r"^```[\w]*\n", "", response.text)
                clean_text = re.sub(r"\s*```$", "", clean_text)
                clean_text = clean_text.strip()

                try:
                    data = json.loads(clean_text)
                    cases_data = (
                        data.get("cases", [])
                        if isinstance(data, dict) and "cases" in data
                        else [data]
                        if isinstance(data, dict)
                        else []
                    )

                    for case in cases_data:
                        tc = type("obj", (), {
                            "case_id": case.get("case_id", ""),
                            "operation_id": case.get("operation_id", ""),
                            "technique": Technique(case.get("technique", "functional")),
                            "description": case.get("description", ""),
                            "steps": [],
                            "assertions": case.get("assertions", []),
                            "expected_status": case.get("expected_status"),
                            "oracle_rules": case.get("oracle_rules", []),
                            "metadata": case.get("metadata", {}),
                            "generated_by": "generator",
                        })

                        for step_data in case.get("steps", []):
                            rs = type("obj", (), {
                                "method": step_data.get("method", "GET"),
                                "path": step_data.get("path", "/"),
                                "body": step_data.get("body"),
                                "media_type": "application/json",
                                "expected_status": step_data.get("expected_status", 200),
                            })
                            tc.steps.append(rs)  # type: ignore[attr-defined]

                        generated.append(tc)

                except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                    pass

            return generated

        except Exception:
            raise


class ValidatorAgent:
    """Validates test cases and executes them against a local mock API."""

    name = "validator"

    def run(self, context, cases):
        valid = 0
        failed = 0
        errors = []

        try:
            server = MockAPIServer(port=11435)
            server.start()
            time.sleep(1)

            engine = ExecutionEngine(
                base_url="http://127.0.0.1:11435", timeout=30.0
            )

            for case in cases:
                try:
                    engine.reset()
                except Exception:
                    pass

                record = engine.execute(case)

                if record.error is None and record.steps[0].status_code is not None:
                    valid += 1
                else:
                    failed += 1
                    errors.append(record.error or "unknown error")

            server.stop()

            return {"valid": valid, "failed": failed, "errors": errors}

        except Exception:
            raise


class DebuggerAgent:
    """Analyzes execution failures and produces diagnostic findings."""

    name = "debugger"

    def run(self, failed_count, execution_results):
        findings = []

        for i in range(min(failed_count, len(execution_results))):
            finding = {
                "case_id": execution_results[i].get("case_id", f"case_{i}") if i < len(execution_results) else f"case_{i}",
                "status_code": execution_results[i].get("status_code"),
                "latency_ms": execution_results[i].get("latency_ms", 0),
                "error": execution_results[i].get("error", "unknown")[:200],
                "suggested_causes": [],
            }

            error_str = finding["error"].lower()
            if "404" in error_str or "not found" in error_str:
                finding["suggested_causes"].append("invalid operation ID or path")
            if "400" in error_str or "bad request" in error_str:
                finding["suggested_causes"].append("invalid request body or parameters")
            if "connection" in error_str or "timeout" in error_str:
                finding["suggested_causes"].append("mock API server not running or unreachable")
            if "json" in error_str.lower() and "parse" in error_str.lower():
                finding["suggested_causes"].append("malformed JSON in test case or mock response")
            if not finding["error"]:
                finding["suggested_causes"].append("no error recorded - examine execution pipeline")

            findings.append(finding)

        return findings


class MultiAgentCoordinator:
    """Coordinates multi-agent API testing workflow."""

    def run(self, dataset_path: str | Path) -> dict[str, Any]:
        run_id = new_run_id()
        dataset_hash = compute_dataset_hash(dataset_path)

        # Step 1: Planner
        print("[coordinator] Step 1: Planner")
        try:
            plan = self._run_planner(dataset_path)
            plan_items = len(plan.items) if hasattr(plan, 'items') else 0
            print(f"  -> {plan_items} plan items generated")
        except Exception as e:
            return {"error": f"Planner failed: {e}"}

        # Step 2: Generator
        print("[coordinator] Step 2: Generator")
        try:
            cases = self._run_generator(plan)
            print(f"  -> {len(cases)} test cases generated")
        except Exception as e:
            return {"error": f"Generator failed: {e}"}

        # Step 3: Validator
        print("[coordinator] Step 3: Validator")
        try:
            server = MockAPIServer(port=11435)
            server.start()
            time.sleep(1)

            engine = ExecutionEngine(
                base_url="http://127.0.0.1:11435", timeout=30.0
            )

            executed = []
            for case in cases:
                try:
                    engine.reset()
                except Exception:
                    pass

                record = engine.execute(case)
                executed.append(
                    {
                        "case_id": case.case_id,
                        "operation_id": case.operation_id,
                        "technique": case.technique.value,
                        "expected_status": case.expected_status,
                        "status_code": record.steps[0].status_code if record.steps else None,
                        "latency_ms": record.steps[0].duration_ms if record.steps else 0,
                        "error": record.error,
                        "success": record.error is None and record.steps[0].status_code is not None,
                    }
                )

            server.stop()

            passed = sum(1 for r in executed if r["success"])
            failed = len(executed) - passed

            print(f"  -> {len(executed)} cases executed, {passed} passed, {failed} failed")
        except Exception as e:
            return {"error": f"Validator failed: {e}"}

        # Step 4: Debugger
        print("[coordinator] Step 4: Debugger")
        try:
            failed_list = [e for e in executed if not e["success"]]
            if failed_list:
                findings = self._run_debugger(failed_cases=failed_list, execution_results=executed)
                print(f"  -> {len(findings)} diagnostic findings")
            else:
                print("  -> No failures to debug")
        except Exception:
            pass

        return {
            "run_id": run_id,
            "dataset_path": str(dataset_path),
            "dataset_hash": dataset_hash,
            "model_name": "qwen2.5:1.5b",
            "ollama_version": "0.40.16",
            "spec_version": "",
            "agent_steps": [],
            "total_duration_ms": 0,
            "error": None,
            "metadata": {},
        }

    def _run_planner(self, dataset_path: str | Path):
        from agenticapi.spec.loader import load_spec
        spec = load_spec(dataset_path)
        return type("obj", (), {"items": [type("obj", (), {"operation_id": op.operation_id}) for op in spec.operations]})()

    def _run_generator(self, plan):
        from agenticapi.phase2c import SingleAgentPipeline
        pipeline = SingleAgentPipeline(model="qwen2.5:1.5b")
        return pipeline.generate_test_cases(
            load_spec("/home/isha/Desktop/ai_re-main/datasets/shop_openapi3.json"),
            operations=[op.operation_id for op in self._run_planner("/home/isha/Desktop/ai_re-main/datasets/shop_openapi3.json").items]
        )

    def _run_debugger(self, failed_cases, execution_results):
        findings = []
        for i in range(min(len(failed_cases), len(execution_results))):
            finding = {
                "case_id": execution_results[i].get("case_id", f"case_{i}") if i < len(execution_results) else f"case_{i}",
                "status_code": execution_results[i].get("status_code"),
                "latency_ms": execution_results[i].get("latency_ms", 0),
                "error": execution_results[i].get("error", "unknown")[:200],
                "suggested_causes": [],
            }
            error_str = finding["error"].lower()
            if "404" in error_str or "not found" in error_str:
                finding["suggested_causes"].append("invalid operation ID or path")
            if "400" in error_str or "bad request" in error_str:
                finding["suggested_causes"].append("invalid request body or parameters")
            if "connection" in error_str or "timeout" in error_str:
                finding["suggested_causes"].append("mock API server not running or unreachable")
            if "json" in error_str.lower() and "parse" in error_str.lower():
                finding["suggested_causes"].append("malformed JSON in test case or mock response")
            if not finding["error"]:
                finding["suggested_causes"].append("no error recorded - examine execution pipeline")
            findings.append(finding)
        return findings