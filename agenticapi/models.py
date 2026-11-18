"""Typed data contracts shared by the AgenticAPI pipeline.

The contracts are intentionally dependency-light dataclasses.  They are the
stable seam between the spec layer, agents, execution layer, and evaluation
harness.  Everything is JSON-serialisable through :func:`jsonable`.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any


class Technique(str, Enum):
    FUNCTIONAL = "functional"
    NEGATIVE = "negative"
    BOUNDARY = "boundary"
    AUTH = "auth"
    AUTHZ = "authz"
    STATEFUL = "stateful"
    BUSINESS_RULE = "business_rule"
    IDEMPOTENCY = "idempotency"


class Outcome(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"
    INVALID_TEST = "INVALID_TEST"
    INCONCLUSIVE = "INCONCLUSIVE"


class FaultCategory(str, Enum):
    STATUS = "status"
    SCHEMA = "schema"
    BOUNDARY = "boundary"
    AUTH = "auth"
    AUTHZ = "authz"
    STATE = "state"
    BUSINESS_RULE = "business_rule"
    IDEMPOTENCY = "idempotency"


class ConditionStatus(str, Enum):
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


class LLMUnavailable(RuntimeError):
    """Raised when a real LLM call is requested without usable credentials."""


def jsonable(value: Any) -> Any:
    """Recursively convert dataclasses/enums/paths into JSON-safe values."""
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: jsonable(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    return value


def write_json(path: Path, value: Any) -> None:
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(jsonable(value), indent=2, sort_keys=True), encoding="utf-8")


def read_json(path: Path) -> Any:
    import json

    return json.loads(path.read_text(encoding="utf-8"))


@dataclass(slots=True)
class Parameter:
    name: str
    location: str
    required: bool = False
    schema: dict[str, Any] = field(default_factory=dict)
    description: str = ""
    example: Any = None

    def to_dict(self) -> dict[str, Any]:
        return jsonable(self)

    @property
    def is_path(self) -> bool:
        return self.location == "path"

    @property
    def is_query(self) -> bool:
        return self.location == "query"

    @property
    def is_header(self) -> bool:
        return self.location == "header"

    @property
    def is_form(self) -> bool:
        return self.location == "formData"


@dataclass(slots=True)
class RequestBody:
    required: bool = False
    content: dict[str, dict[str, Any]] = field(default_factory=dict)
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return jsonable(self)

    @property
    def media_types(self) -> list[str]:
        return list(self.content)

    @property
    def primary_media_type(self) -> str:
        return next(iter(self.content), "application/json")

    def schema_for(self, media_type: str | None = None) -> dict[str, Any]:
        if media_type and media_type in self.content:
            return self.content[media_type].get("schema", {})
        first = next(iter(self.content.values()), {})
        return first.get("schema", {})


@dataclass(slots=True)
class ResponseSpec:
    status_code: str
    description: str = ""
    content: dict[str, dict[str, Any]] = field(default_factory=dict)
    headers: dict[str, Any] = field(default_factory=dict)

    def schema_for(self, media_type: str | None = None) -> dict[str, Any]:
        if media_type and media_type in self.content:
            return self.content[media_type].get("schema", {})
        first = next(iter(self.content.values()), {})
        return first.get("schema", {})

    def to_dict(self) -> dict[str, Any]:
        return jsonable(self)


@dataclass(slots=True)
class SecurityScheme:
    name: str
    type: str
    scheme: str = ""
    bearer_format: str = ""
    flows: dict[str, Any] = field(default_factory=dict)
    location: str = ""
    parameter_name: str = ""


@dataclass(slots=True)
class SecurityRequirement:
    scheme: str
    scopes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Operation:
    operation_id: str
    method: str
    path: str
    summary: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)
    parameters: list[Parameter] = field(default_factory=list)
    request_body: RequestBody | None = None
    responses: dict[str, ResponseSpec] = field(default_factory=dict)
    security: list[SecurityRequirement] = field(default_factory=list)
    servers: list[str] = field(default_factory=list)
    extensions: dict[str, Any] = field(default_factory=dict)

    def parameters_in(self, location: str) -> list[Parameter]:
        return [p for p in self.parameters if p.location == location]

    @property
    def path_parameters(self) -> list[Parameter]:
        return self.parameters_in("path")

    @property
    def query_parameters(self) -> list[Parameter]:
        return self.parameters_in("query")

    @property
    def header_parameters(self) -> list[Parameter]:
        return self.parameters_in("header")

    @property
    def form_parameters(self) -> list[Parameter]:
        return self.parameters_in("formData")

    @property
    def requires_auth(self) -> bool:
        return bool(self.security)

    @property
    def primary_media_type(self) -> str:
        if self.request_body:
            return self.request_body.primary_media_type
        return "application/json"

    @property
    def success_status(self) -> str:
        for code in self.responses:
            if str(code).startswith("2"):
                return str(code)
        for code in self.responses:
            if str(code) != "default":
                return str(code)
        return "200"

    def response_schema(self, status: str | int | None = None) -> dict[str, Any]:
        code = str(status or self.success_status)
        response = self.responses.get(code)
        if response is None:
            for key in ("default", "200"):
                if key in self.responses:
                    response = self.responses[key]
                    break
        return response.schema_for() if response else {}

    def to_dict(self) -> dict[str, Any]:
        return jsonable(self)


@dataclass(slots=True)
class APISpec:
    title: str
    version: str
    openapi_version: str
    base_url: str
    operations: list[Operation] = field(default_factory=list)
    schemas: dict[str, Any] = field(default_factory=dict)
    raw_schemas: dict[str, Any] = field(default_factory=dict)
    security_schemes: dict[str, SecurityScheme] = field(default_factory=dict)
    extensions: dict[str, Any] = field(default_factory=dict)
    source_path: str = ""

    def operation_map(self) -> dict[str, Operation]:
        return {op.operation_id: op for op in self.operations}

    def operation(self, operation_id: str) -> Operation:
        try:
            return self.operation_map()[operation_id]
        except KeyError as exc:
            raise KeyError(f"unknown operation_id: {operation_id}") from exc

    @property
    def schema_names(self) -> list[str]:
        return sorted(self.schemas)

    def to_dict(self) -> dict[str, Any]:
        return jsonable(self)


@dataclass(slots=True)
class GraphEdge:
    source: str
    target: str
    kind: str
    reason: str = ""


@dataclass(slots=True)
class DependencyGraph:
    schema_edges: list[GraphEdge] = field(default_factory=list)
    operation_edges: list[GraphEdge] = field(default_factory=list)
    auth_edges: list[GraphEdge] = field(default_factory=list)
    workflows: list[list[str]] = field(default_factory=list)

    def out_degree(self, operation_id: str) -> int:
        return sum(1 for e in self.operation_edges if e.source == operation_id)

    def in_degree(self, operation_id: str) -> int:
        return sum(1 for e in self.operation_edges if e.target == operation_id)

    def to_dict(self) -> dict[str, Any]:
        return jsonable(self)


@dataclass(slots=True)
class TestPlanItem:
    operation_id: str
    techniques: list[Technique] = field(default_factory=list)
    priority: int = 0
    max_cases: int = 4
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return jsonable(self)


@dataclass(slots=True)
class TestPlan:
    items: list[TestPlanItem] = field(default_factory=list)
    generated_by: str = "deterministic"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return jsonable(self)


@dataclass(slots=True)
class RequestStep:
    method: str
    path: str
    path_params: dict[str, Any] = field(default_factory=dict)
    query: dict[str, Any] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    body: Any = None
    media_type: str = "application/json"
    form: dict[str, Any] = field(default_factory=dict)
    files: dict[str, Any] = field(default_factory=dict)
    auth: str | None = None
    capture: dict[str, str] = field(default_factory=dict)
    expected_status: int | None = None
    label: str = ""

    def to_dict(self) -> dict[str, Any]:
        return jsonable(self)


@dataclass(slots=True)
class Assertion:
    kind: str
    target: str = ""
    expected: Any = None
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return jsonable(self)


@dataclass(slots=True)
class TestCase:
    case_id: str
    operation_id: str
    technique: Technique
    description: str = ""
    steps: list[RequestStep] = field(default_factory=list)
    assertions: list[Assertion] = field(default_factory=list)
    expected_status: int | None = None
    oracle_rules: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    generated_by: str = "deterministic"

    def to_dict(self) -> dict[str, Any]:
        return jsonable(self)


@dataclass(slots=True)
class GeneratedTest:
    case_id: str
    file_path: str
    code: str
    valid: bool = True
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return jsonable(self)


@dataclass(slots=True)
class ExecutionResult:
    case_id: str
    status: str
    duration_ms: float = 0.0
    nodeid: str = ""
    stdout: str = ""
    stderr: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return jsonable(self)


@dataclass(slots=True)
class OracleResult:
    case_id: str
    outcome: Outcome
    failure_kind: str = ""
    messages: list[str] = field(default_factory=list)
    step_results: list[dict[str, Any]] = field(default_factory=list)
    latency_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return jsonable(self)


@dataclass(slots=True)
class Fault:
    fault_id: str
    category: FaultCategory
    description: str
    operation_id: str
    method: str
    path: str
    location: str
    expected_behavior: str
    activation: dict[str, Any] = field(default_factory=dict)
    ground_truth: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return jsonable(self)


@dataclass(slots=True)
class LLMResponse:
    provider: str
    model: str
    text: str = ""
    parsed: Any = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float | None = None
    latency_ms: float = 0.0
    is_llm: bool = False
    error: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def to_dict(self) -> dict[str, Any]:
        return jsonable(self)


@dataclass(slots=True)
class TraceEvent:
    agent: str
    action: str
    summary: str = ""
    duration_ms: float = 0.0
    provider: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return jsonable(self)


@dataclass(slots=True)
class ExperimentConfig:
    name: str = "default"
    condition_id: str = ""
    spec_path: str = "datasets/shop_openapi3.json"
    conditions: list[str] = field(
        default_factory=lambda: ["C0_legacy", "C1_schema", "C2_single_llm", "C3_multi_llm"]
    )
    seeds: list[int] = field(default_factory=lambda: [1, 2, 3])
    fault_ids: list[str] = field(default_factory=list)
    output_dir: str = "artifacts/runs"
    max_cases_per_operation: int = 8
    max_repairs: int = 2
    pytest_timeout_seconds: int = 180
    llm_timeout_seconds: int = 60
    max_llm_calls: int = 60
    max_cost_usd: float = 1.0
    max_cases_total: int = 80
    allow_llm_fallback: bool = False
    llm_provider: str = "openai_compatible"
    llm_model: str = "gpt-4o-mini"
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return jsonable(self)


@dataclass(slots=True)
class ConditionResult:
    condition: str
    seed: int
    status: ConditionStatus
    provider: str = ""
    is_llm: bool = False
    cases_generated: int = 0
    cases_valid: int = 0
    cases_executed: int = 0
    oracle_results: list[OracleResult] = field(default_factory=list)
    execution_results: list[ExecutionResult] = field(default_factory=list)
    fault_results: dict[str, list[OracleResult]] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    llm_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float | None = None
    duration_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)
    artifact_dir: str = ""
    execution_feedback_applied: bool = False

    def to_dict(self) -> dict[str, Any]:
        return jsonable(self)


TestCase.__test__ = False  # type: ignore[attr-defined]


def dedupe_cases(cases: Iterable[TestCase]) -> list[TestCase]:
    seen: set[str] = set()
    result: list[TestCase] = []
    for case in cases:
        key = case.case_id
        if key in seen:
            continue
        seen.add(key)
        result.append(case)
    return result
