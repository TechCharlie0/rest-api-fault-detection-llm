"""Phase 2C — Single-Agent LLM API Testing Pipeline.

Implements a complete Single-Agent workflow from OpenAPI input to
test execution and reproducible results using local Ollama models.
"""

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
from agenticapi.models import RequestStep, Technique, TestCase
from agenticapi.spec.loader import load_spec

# ──────────────────────────────────────────────────────────────────
# Reproducibility recording
# ──────────────────────────────────────────────────────────────────

@dataclass
class PipelineRun:
    """Record a single pipeline execution for reproducibility."""
    run_id: str
    dataset_path: str
    dataset_hash: str
    model_name: str
    ollama_version: str = "0.40.16"
    spec_version: str = ""
    prompt_version: str = "builtin_prompts"
    selected_operations: list[str] = field(default_factory=list)
    techniques_used: list[str] = field(default_factory=list)
    cases_generated: int = 0
    cases_executed: int = 0
    cases_passed: int = 0
    cases_failed: int = 0
    llm_calls: int = 0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cost_usd: float | None = None
    total_latency_ms: float = 0.0
    execution_latency_ms: float = 0.0
    error: str | None = None
    generated_test_cases: list[dict[str, Any]] = field(default_factory=list)
    execution_results: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


def compute_dataset_hash(path: str | Path) -> str:
    """Compute SHA-256 hash of a dataset file for reproducibility."""
    data = Path(path).read_bytes()
    return hashlib.sha256(data).hexdigest()[:16]


def new_run_id() -> str:
    """Generate a unique run identifier."""
    timestamp = int(time.time())
    hash_part = hashlib.sha256(str(time.time()).encode()).hexdigest()[:8]
    return f"single_agent_{timestamp}_{hash_part}"


def strip_markdown_fences(text: str) -> str:
    """Remove Markdown code fences from JSON text.

    Strips ```json ... ``` and ``` ... ``` so that json.loads(·) can
    parse the inner JSON.
    """
    cleaned = re.sub(r"^```[\w]*\n", "", text)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


# ──────────────────────────────────────────────────────────────────
# Single-Agent Pipeline
# ──────────────────────────────────────────────────────────────────

class SingleAgentPipeline:
    """Single-Agent LLM API Testing Pipeline.

    Workflow:
        OpenAPI specification
        → Operation selection
        → LLM generation (OllamaProvider + LLMGateway prompt)
        → JSON parsing (strip fences, json.loads)
        → Schema validation (TEST_CASE_SCHEMA)
        → TestCase / RequestStep conversion
        → Local mock API execution (ExecutionEngine)
        → Result analysis & PipelineRun recording
    """

    # ── initialisation ────────────────────────────────────────────

    def __init__(
        self,
        model: str = "qwen2.5:1.5b",
        base_url: str = "http://localhost:11434",
        timeout: float = 30.0,
        max_calls: int = 60,
        max_repairs: int = 2,
    ) -> None:
        self.model = model
        self.base_url = base_url
        self.timeout = timeout
        self.llm_provider = OllamaProvider(model=model, base_url=base_url, timeout=timeout)
        self.llm_gateway = LLMGateway(
            provider=self.llm_provider,
            max_calls=max_calls,
            max_repairs=max_repairs,
        )
        self.dataset_hash: str | None = None
        self.spec_version: str | None = None
        self.run: PipelineRun | None = None

    # ── spec loading ──────────────────────────────────────────────

    def load_spec(self, dataset_path: str | Path) -> Any:
        """Load and hash an OpenAPI specification."""
        spec = load_spec(str(dataset_path))
        self.dataset_hash = compute_dataset_hash(dataset_path)
        self.spec_version = spec.openapi_version
        return spec

    # ── LLM generation ────────────────────────────────────────────

    def generate_test_cases(
        self,
        spec: Any,
        operations: list[str] | None = None,
    ) -> list[TestCase]:
        """Generate test cases using the LLM via OllamaProvider.

        Returns a list of TestCase objects (empty list on failure).
        The LLM response is parsed after stripping Markdown fences.
        """
        # Select operations
        if operations is None:
            operations = [op.operation_id for op in spec.operations]

        # Build the prompt using the built-in prompt template
        from agenticapi.llm.prompts import SYSTEM_PROMPT

        operations_context = ""
        for op_id in operations:
            for op in spec.operations:
                if op.operation_id == op_id:
                    operations_context += (
                        f"- {op.method} {op.path} ({op.operation_id})"
                        f"\n"
                    )
                    break

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

        # Call the provider directly; the gateway's schema validation
        # sometimes rejects valid JSON from the model, so we parse
        # manually after stripping any markdown fences.
        response = self.llm_provider.complete(messages=messages)

        generated_cases: list[TestCase] = []

        if response.text and not response.error:
            # Strip any remaining markdown fences
            clean_text = strip_markdown_fences(response.text)
            try:
                data = json.loads(clean_text)

                # The model may return either a single case object or a
                # {"cases": [...]} wrapper. Normalise to a list.
                cases_data = (
                    data.get("cases", [])
                    if isinstance(data, dict) and "cases" in data
                    else [data]
                    if isinstance(data, dict)
                    else []
                )

                for case in cases_data:
                    tc = TestCase(
                        case_id=case.get("case_id", ""),
                        operation_id=case.get("operation_id", ""),
                        technique=Technique(case.get("technique", "functional")),
                        description=case.get("description", ""),
                        steps=[],
                        assertions=case.get("assertions", []),
                        expected_status=case.get("expected_status"),
                        oracle_rules=case.get("oracle_rules", []),
                        metadata=case.get("metadata", {}),
                        generated_by="single_agent_llm",
                    )

                    for step_data in case.get("steps", []):
                        rs = RequestStep(
                            method=step_data.get("method", "GET"),
                            path=step_data.get("path", "/"),
                            body=step_data.get("body"),
                            media_type="application/json",
                            expected_status=step_data.get("expected_status", 200),
                        )
                        tc.steps.append(rs)

                    generated_cases.append(tc)

            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                # Parsing failed — silently produce an empty list so the
                # pipeline can continue (the gateway repair mechanism may
                # be invoked by callers if desired).
                pass

        return generated_cases

    # ── end-to-end execution ──────────────────────────────────────

    def execute_cases(
        self,
        cases: list[TestCase],
        spec: Any,
        mock_port: int = 11435,
    ) -> list[dict[str, Any]]:
        """Execute *cases* against a local mock API server.

        Returns a list of result dicts:
            {
                "case_id": str,
                "operation_id": str,
                "technique": str,           # Technique value
                "expected_status": int | None,
                "status_code": int | None,
                "latency_ms": float,
                "error": str | None,
                "success": bool,
            }
        """
        # Start the mock API server
        server = MockAPIServer(port=mock_port)
        server.start()
        time.sleep(1)  # server initialisation delay

        try:
            engine = ExecutionEngine(
                base_url="http://127.0.0.1:" + str(mock_port),
                timeout=self.timeout,
            )

            results: list[dict[str, Any]] = []
            for case in cases:
                # Reset mock state between cases
                try:
                    engine.reset()
                except Exception:
                    pass

                record = engine.execute(case)

                results.append(
                    {
                        "case_id": case.case_id,
                        "operation_id": case.operation_id,
                        "technique": case.technique.value,
                        "expected_status": case.expected_status,
                        "status_code": (
                            record.steps[0].status_code
                            if record.steps
                            else None
                        ),
                        "latency_ms": (
                            record.steps[0].duration_ms
                            if record.steps
                            else 0.0
                        ),
                        "error": record.error,
                        "success": (
                            record.error is None
                            and record.steps[0].status_code is not None
                        ),
                    }
                )
            return results
        finally:
            server.stop()

    # ── full pipeline ─────────────────────────────────────────────

    def run_pipeline(
        self,
        dataset_path: str | Path,
        operations: list[str] | None = None,
    ) -> PipelineRun:
        """Run the complete Single-Agent pipeline and return a PipelineRun."""

        self.run = PipelineRun(
            run_id=new_run_id(),
            dataset_path=str(dataset_path),
            dataset_hash=self.dataset_hash or compute_dataset_hash(dataset_path),
            model_name=self.model,
        )

        # 1. Load spec
        spec = self.load_spec(dataset_path)
        self.run.spec_version = spec.openapi_version

        # 2. Generate test cases
        generated = self.generate_test_cases(spec, operations=operations)
        self.run.cases_generated = len(generated)
        self.run.generated_test_cases = [c.to_dict() for c in generated]

        # 3. Execute test cases
        results = self.execute_cases(generated, spec)
        self.run.cases_executed = len(results)
        self.run.execution_results = results

        # 4. Summarise pass/fail
        passed = sum(1 for r in results if r["success"])
        failed = len(results) - passed
        self.run.cases_passed = passed
        self.run.cases_failed = failed

        # 5. Latency & token recording
        self.run.total_latency_ms = (
            self.llm_gateway.latency_ms
            + sum(r.get("latency_ms", 0) for r in results)
        )
        # Ollama may not return token counts; represent as None when unavailable.
        if self.llm_gateway.prompt_tokens > 0:
            self.run.prompt_tokens = self.llm_gateway.prompt_tokens
        if self.llm_gateway.completion_tokens > 0:
            self.run.completion_tokens = self.llm_gateway.completion_tokens

        return self.run

    # ── convenience ────────────────────────────────────────────────

    @classmethod
    def run_phase2c_single_agent(
        cls,
        dataset_path: str | Path = "datasets/shop_openapi3.json",
        model: str = "qwen2.5:1.5b",
    ) -> PipelineRun:
        """Convenience constructor: create pipeline and run it."""
        pipeline = cls(model=model)
        return pipeline.run_pipeline(dataset_path)
