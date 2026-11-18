"""Test-case generator: deterministic builders plus optional LLM cases."""

from __future__ import annotations

import copy
import random
import re
import time
from typing import Any

from agenticapi.agents.base import AgentContext, BaseAgent
from agenticapi.agents.spec_analyst import SpecAnalysis
from agenticapi.models import (
    Assertion,
    Operation,
    RequestStep,
    Technique,
    TestCase,
    TestPlan,
    TestPlanItem,
)
from agenticapi.spec.schema import resolve_schema, sample_schema

_MISSING = object()
PATH_FIXTURES = {
    "product_id": "p2",
    "order_id": "o2",
    "username": "alice",
    "petId": "1",
}
BODY_OVERRIDES: dict[str, dict[str, Any]] = {
    "login": {"username": "alice", "password": "alicepw"},
    "create_order": {"product_id": "p1", "quantity": 1},
    "create_product": {
        "name": "Generated Widget",
        "price": 12.5,
        "stock": 9,
        "category": "electronics",
    },
    "update_product": {
        "name": "Updated Widget",
        "price": 13.5,
        "stock": 4,
        "category": "books",
    },
    "update_order": {"status": "paid"},
    "update_user": {"name": "Alice Cooper", "email": "alice@example.com"},
}
ADMIN_OPERATIONS = {"create_product", "update_product", "delete_product", "upload_product_image"}


class LLMGenerationError(RuntimeError):
    """Raised when an LLM condition produced no usable cases and fallback is off."""


def _media_type(op: Operation) -> str:
    return op.primary_media_type if op.request_body else "application/json"


def _path_for(op: Operation, overrides: dict[str, str] | None = None) -> str:
    path = op.path
    values = dict(PATH_FIXTURES)
    if overrides:
        values.update(overrides)
    for name, value in values.items():
        path = path.replace("{" + name + "}", str(value))
    return path


def _path_params(op: Operation, overrides: dict[str, str] | None = None) -> dict[str, str]:
    values = dict(PATH_FIXTURES)
    if overrides:
        values.update(overrides)
    return {param.name: values.get(param.name, "sample") for param in op.path_parameters}


def _op(op: Operation, method: str, path: str) -> bool:
    """Check if an operation matches a given method and path pattern.

    Uses generic method+path matching instead of hardcoded operation_id,
    so the same generator works with any OpenAPI spec.

    Examples:
        _op(op, "GET", "/products")       matches list_products
        _op(op, "POST", "/products")      matches create_product
        _op(op, "GET", "/products/{product_id}")  matches get_product
        _op(op, "POST", "/orders")        matches create_order
        _op(op, "GET", "/orders/{order_id}")  matches get_order
    """
    return op.method == method and op.path == path


def _op_re(op: Operation, method: str, pattern: str) -> bool:
    """Check if an operation matches a method and regex pattern on path.

    Examples:
        _op_re(op, "GET", r"/users/{username}")  matches get_user / update_user
        _op_re(op, "POST", r"/auth/login")       matches login
    """
    return op.method == method and re.search(pattern, op.path) is not None


def _query_values(op: Operation, include_optional: bool = False) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for param in op.query_parameters:
        if not param.required and not include_optional:
            continue
        values[param.name] = sample_schema(
            resolve_schema(param.schema, {}),
            {},
            name_hint=param.name,
        )
    return values


def _body_for(context: AgentContext, op: Operation, *, overrides: dict[str, Any] | None = None) -> Any:
    if not op.request_body:
        return None
    media = _media_type(op)
    schema = op.request_body.schema_for(media)
    body: dict[str, Any] = {}
    sampled = sample_schema(
        schema,
        context.spec.raw_schemas,
        name_hint=op.operation_id,
    )
    if isinstance(sampled, dict):
        body.update(sampled)
    body.update(BODY_OVERRIDES.get(op.operation_id, {}))
    if overrides:
        body.update(overrides)
    return body


def _auth_for(op: Operation, *, role: str | None = None, anonymous: bool = False) -> str | None:
    if anonymous or not op.requires_auth:
        return None
    if role == "admin" or (
        (op.method == "POST" and op.path == "/products")
        or (op.method == "PUT" and op.path == "/products/{product_id}")
        or (op.method == "DELETE" and op.path == "/products/{product_id}")
        or (op.method == "POST" and op.path.endswith("/image"))
    ):
        return "admin"
    return "user"


def _request(
    context: AgentContext,
    op: Operation,
    *,
    body: Any = _MISSING,
    query: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    auth: Any = _MISSING,
    path_overrides: dict[str, str] | None = None,
    include_optional_query: bool = False,
    expected_status: int | None = None,
    label: str = "",
) -> RequestStep:
    media = _media_type(op)
    if body is _MISSING:
        body = _body_for(context, op) if op.request_body else None
    step = RequestStep(
        method=op.method,
        path=_path_for(op, path_overrides),
        path_params=_path_params(op, path_overrides),
        query=query if query is not None else _query_values(op, include_optional_query),
        headers=dict(headers or {}),
        auth=_auth_for(op) if auth is _MISSING else auth,
        media_type=media,
        expected_status=expected_status,
        label=label or op.operation_id,
    )
    if body is not _MISSING:
        if body is not None and media == "application/json":
            step.body = copy.deepcopy(body)
        elif body is not None and "x-www-form-urlencoded" in media:
            step.form = copy.deepcopy(body)
    if op.request_body and media == "multipart/form-data" and body is not None:
        schema = resolve_schema(op.request_body.schema_for(media), context.spec.raw_schemas)
        properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
        if "caption" in properties:
            step.form["caption"] = "generated test image"
        for name, child in properties.items():
            child = resolve_schema(child, context.spec.raw_schemas)
            if isinstance(child, dict) and child.get("format") == "binary":
                step.files[name] = {
                    "filename": "sample.png",
                    "content": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=",
                    "content_type": "image/png",
                }
    if op.form_parameters and body is not _MISSING and body is not None:
        step.form = copy.deepcopy(body) if isinstance(body, dict) else {}
    return step


def _assert_status(case: TestCase, expected: int | None) -> None:
    if expected is not None:
        case.assertions.append(
            Assertion(kind="status", target="", expected=expected, description="HTTP status")
        )


def _assert_schema(case: TestCase, op: Operation, status: int | str) -> None:
    schema = op.response_schema(str(status))
    if schema:
        case.assertions.append(
            Assertion(
                kind="schema",
                target=str(status),
                description="response body matches the declared schema",
            )
        )


def _case(
    op: Operation,
    technique: Technique,
    *,
    description: str,
    steps: list[RequestStep],
    expected_status: int | None,
    oracle_rules: list[str] | None = None,
    generated_by: str = "deterministic",
    metadata: dict[str, Any] | None = None,
) -> TestCase:
    case = TestCase(
        case_id=f"{op.operation_id}__{technique.value}",
        operation_id=op.operation_id,
        technique=technique,
        description=description,
        steps=steps,
        expected_status=expected_status,
        oracle_rules=list(oracle_rules or []),
        generated_by=generated_by,
        metadata=dict(metadata or {}),
    )
    _assert_status(case, expected_status)
    if expected_status is not None and 200 <= expected_status < 300:
        _assert_schema(case, op, expected_status)
    elif expected_status in {400, 401, 403, 404, 409, 422}:
        _assert_schema(case, op, expected_status)
    return case


def _functional(context: AgentContext, op: Operation, suite: str) -> TestCase:
    status = int(op.success_status)
    path_overrides = None
    if op.method == "DELETE" and op.path == "/products/{product_id}":
        path_overrides = {"product_id": "p3"}
    elif op.method == "GET" and op.path == "/products/{product_id}":
        path_overrides = {"product_id": "p1"}
    body = {"status": "shipped"} if op.method in ("PATCH", "POST") and op.path == "/orders/{order_id}" else _MISSING
    if context.extra.get("randomize"):
        body = _randomized_body(context, op)
    step = _request(
        context,
        op,
        body=body,
        path_overrides=path_overrides,
        include_optional_query=bool(context.extra.get("randomize")),
        expected_status=status,
    )
    if context.extra.get("randomize") and op.method == "GET" and op.path == "/products":
        step.query["limit"] = random.Random(int(context.extra.get("seed", 1))).randint(1, 10)
    return _case(
        op,
        Technique.FUNCTIONAL,
        description=f"Valid request for {op.operation_id}",
        steps=[step],
        expected_status=status,
        metadata={"suite": suite},
    )


def _randomized_body(context: AgentContext, op: Operation) -> Any:
    body = _body_for(context, op)
    if not isinstance(body, dict) or op.method == "POST" and op.path == "/auth/login":
        return body
    if op.method in ("PATCH", "POST") and op.path == "/orders/{order_id}":
        return {"status": "shipped"}
    rng = random.Random(int(context.extra.get("seed", 1)))
    schema = resolve_schema(
        op.request_body.schema_for(_media_type(op)) if op.request_body else {},
        context.spec.raw_schemas,
    )
    properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
    for name, child in properties.items():
        child = resolve_schema(child, context.spec.raw_schemas)
        if not isinstance(child, dict) or name not in body:
            continue
        if child.get("enum"):
            body[name] = rng.choice(child["enum"])
        elif child.get("type") == "integer":
            minimum = int(child.get("minimum", 1))
            maximum = int(child.get("maximum", minimum + 5))
            if op.method == "POST" and op.path == "/orders" and name == "quantity":
                maximum = min(maximum, 3)
            body[name] = rng.randint(minimum, max(minimum, maximum))
        elif child.get("type") == "number":
            minimum_number = float(child.get("minimum", 1.0))
            body[name] = round(
                max(minimum_number, rng.uniform(minimum_number, minimum_number + 50)),
                2,
            )
        elif child.get("type") == "string" and child.get("format") == "email":
            body[name] = f"user{context.extra.get('seed', 1)}@example.com"
        elif child.get("type") == "string" and "example" not in child:
            body[name] = f"sample-{context.extra.get('seed', 1)}-{rng.randint(1, 999)}"
    return body


def _negative(context: AgentContext, op: Operation, suite: str) -> TestCase | None:
    if op.request_body and "multipart/form-data" in _media_type(op):
        return _case(
            op,
            Technique.NEGATIVE,
            description="Multipart upload omits the required file",
            steps=[
                _request(
                    context,
                    op,
                    body=None,
                    expected_status=400,
                )
            ],
            expected_status=400,
            metadata={"suite": suite, "mutation": "missing_file"},
        )
    body = _body_for(context, op)
    if isinstance(body, dict) and body:
        schema = resolve_schema(
            op.request_body.schema_for(_media_type(op)) if op.request_body else {},
            context.spec.raw_schemas,
        )
        properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
        for name in body:
            child = resolve_schema(properties.get(name, {}), context.spec.raw_schemas)
            if not isinstance(child, dict):
                continue
            kind = child.get("type")
            if kind == "integer":
                body[name] = "not-an-integer"
            elif kind == "number":
                body[name] = "not-a-number"
            elif kind == "boolean":
                body[name] = "not-a-boolean"
            elif kind == "string":
                body[name] = 12345
            elif kind == "array":
                body[name] = "not-an-array"
            else:
                continue
            return _case(
                op,
                Technique.NEGATIVE,
                description=f"Body field {name!r} has the wrong type",
                steps=[_request(context, op, body=body, expected_status=400)],
                expected_status=400,
                metadata={"suite": suite, "mutation": f"type:{name}"},
            )
    for param in op.query_parameters:
        if param.required:
            query = _query_values(op)
            query[param.name] = "not-a-valid-value"
            return _case(
                op,
                Technique.NEGATIVE,
                description=f"Query parameter {param.name!r} is invalid",
                steps=[_request(context, op, query=query, expected_status=400)],
                expected_status=400,
                metadata={"suite": suite, "mutation": f"query:{param.name}"},
            )
    return None


def _boundary(context: AgentContext, op: Operation, suite: str) -> TestCase | None:
    body = _body_for(context, op)
    schema = resolve_schema(
        op.request_body.schema_for(_media_type(op)) if op.request_body else {},
        context.spec.raw_schemas,
    )
    properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
    if isinstance(body, dict):
        for name, value in body.items():
            child = resolve_schema(properties.get(name, {}), context.spec.raw_schemas)
            if not isinstance(child, dict):
                continue
            if child.get("type") == "integer" and isinstance(value, int) and not isinstance(value, bool):
                mutated = dict(body)
                if "maximum" in child and value >= int(child["maximum"]):
                    mutated[name] = int(child["maximum"]) + 1
                elif isinstance(child.get("minimum"), (int, float)) and value <= int(child["minimum"]):
                    mutated[name] = max(0, int(child["minimum"]) - 1)
                else:
                    mutated[name] = value + 10_000
                return _case(
                    op,
                    Technique.BOUNDARY,
                    description=f"Body field {name!r} outside its integer bounds",
                    steps=[_request(context, op, body=mutated, expected_status=400)],
                    expected_status=400,
                    metadata={"suite": suite, "mutation": f"boundary:{name}"},
                )
            if child.get("type") == "number" and isinstance(value, (int, float)) and not isinstance(value, bool):
                mutated = dict(body)
                minimum = child.get("minimum")
                mutated[name] = 0 if isinstance(minimum, (int, float)) and minimum > 0 else -1
                return _case(
                    op,
                    Technique.BOUNDARY,
                    description=f"Body field {name!r} outside its numeric bounds",
                    steps=[_request(context, op, body=mutated, expected_status=400)],
                    expected_status=400,
                    metadata={"suite": suite, "mutation": f"boundary:{name}"},
                )
    for param in op.query_parameters:
        child = resolve_schema(param.schema, context.spec.raw_schemas)
        if isinstance(child, dict) and child.get("type") == "integer" and child.get("minimum") is not None:
            query = _query_values(op)
            query[param.name] = int(child["minimum"]) - 1
            return _case(
                op,
                Technique.BOUNDARY,
                description=f"Query parameter {param.name!r} is below its minimum",
                steps=[_request(context, op, query=query, expected_status=400)],
                expected_status=400,
                metadata={"suite": suite, "mutation": f"boundary:{param.name}"},
            )
    return None


def _auth(context: AgentContext, op: Operation, suite: str) -> TestCase | None:
    if not op.requires_auth:
        return None
    return _case(
        op,
        Technique.AUTH,
        description="Protected operation without credentials",
        steps=[_request(context, op, auth=None, expected_status=401)],
        expected_status=401,
        metadata={"suite": suite},
    )


def _authz(context: AgentContext, op: Operation, suite: str) -> TestCase | None:
    if not op.requires_auth:
        return None
    if (
        (op.method == "POST" and op.path == "/products")
        or (op.method == "PUT" and op.path == "/products/{product_id}")
        or (op.method == "DELETE" and op.path == "/products/{product_id}")
        or (op.method == "POST" and op.path.endswith("/image"))
    ):
        return _case(
            op,
            Technique.AUTHZ,
            description="Non-admin user attempts an admin-only operation",
            steps=[_request(context, op, auth="user", expected_status=403)],
            expected_status=403,
            metadata={"suite": suite},
        )
    if (op.method == "GET" and op.path == "/orders/{order_id}") or (op.method in ("PATCH", "POST") and op.path == "/orders/{order_id}"):
        return _case(
            op,
            Technique.AUTHZ,
            description="User requests another user's order",
            steps=[
                _request(
                    context,
                    op,
                    path_overrides={"order_id": "o1"},
                    auth="user",
                    expected_status=403,
                )
            ],
            expected_status=403,
            metadata={"suite": suite, "owner": "bob"},
        )
    if (op.method == "GET" and _op_re(op, "GET", r"/users/{username}")) or (op.method == "PUT" and _op_re(op, "PUT", r"/users/{username}")):
        return _case(
            op,
            Technique.AUTHZ,
            description="User requests another user's profile",
            steps=[
                _request(
                    context,
                    op,
                    path_overrides={"username": "bob"},
                    auth="user",
                    expected_status=403,
                )
            ],
            expected_status=403,
            metadata={"suite": suite, "owner": "bob"},
        )
    return None


def _stateful(context: AgentContext, op: Operation, suite: str) -> TestCase | None:
    if op.method == "POST" and op.path == "/orders":
        first = _request(
            context,
            op,
            body=_body_for(context, op),
            headers={"Idempotency-Key": "stateful-order-key"},
            expected_status=201,
        )
        first.capture = {"order_id": "body.id"}
        get_order = context.spec.operation("get_order")
        second = _request(
            context,
            get_order,
            path_overrides={"order_id": "${order_id}"},
            auth="user",
            expected_status=200,
        )
        update_order = context.spec.operation("update_order")
        third = _request(
            context,
            update_order,
            path_overrides={"order_id": "${order_id}"},
            body={"status": "paid"},
            auth="user",
            expected_status=200,
        )
        case = TestCase(
            case_id="create_order__stateful",
            operation_id=op.operation_id,
            technique=Technique.STATEFUL,
            description="Create an order, read it back, then advance its status",
            steps=[first, second, third],
            expected_status=201,
            generated_by="deterministic",
            metadata={"suite": suite},
        )
        _assert_status(case, 200)
        return case
    if op.method == "POST" and op.path == "/products":
        first = _request(
            context,
            op,
            body=_body_for(context, op),
            expected_status=201,
        )
        first.capture = {"product_id": "body.id"}
        get_product = context.spec.operation("get_product")
        second = _request(
            context,
            get_product,
            path_overrides={"product_id": "${product_id}"},
            expected_status=200,
        )
        delete_product = context.spec.operation("delete_product")
        third = _request(
            context,
            delete_product,
            path_overrides={"product_id": "${product_id}"},
            expected_status=204,
        )
        fourth = _request(
            context,
            get_product,
            path_overrides={"product_id": "${product_id}"},
            expected_status=404,
        )
        case = TestCase(
            case_id="create_product__stateful",
            operation_id=op.operation_id,
            technique=Technique.STATEFUL,
            description="Create a product, read it, delete it, then verify it is gone",
            steps=[first, second, third, fourth],
            expected_status=201,
            generated_by="deterministic",
            metadata={"suite": suite},
        )
        _assert_status(case, 404)
        return case
    return None


def _idempotency(context: AgentContext, op: Operation, suite: str) -> TestCase | None:
    if not (op.method == "POST" and op.path == "/orders"):
        return None
    body = _body_for(context, op)
    first = _request(
        context,
        op,
        body=body,
        headers={"Idempotency-Key": "idem-fixed-key"},
        expected_status=201,
    )
    first.capture = {"first_order_id": "body.id"}
    second = _request(
        context,
        op,
        body=body,
        headers={"Idempotency-Key": "idem-fixed-key"},
        expected_status=201,
    )
    second.capture = {"second_order_id": "body.id"}
    case = TestCase(
        case_id="create_order__idempotency",
        operation_id=op.operation_id,
        technique=Technique.IDEMPOTENCY,
        description="Repeating a create with the same Idempotency-Key returns the same order",
        steps=[first, second],
        expected_status=201,
        oracle_rules=["idempotent_create"],
        generated_by="deterministic",
        metadata={"suite": suite, "same_fields": ["first_order_id", "second_order_id"]},
    )
    _assert_status(case, 201)
    return case


def _business_rule(context: AgentContext, op: Operation, suite: str) -> TestCase | None:
    rules = context.spec.extensions.get("x-agenticapi-business-rules", [])
    for rule in rules:
        if not isinstance(rule, dict) or rule.get("operation_id") != op.operation_id:
            continue
        oracle = str(rule.get("oracle", ""))
        if oracle == "quantity_le_stock":
            body = _body_for(context, op)
            body["product_id"] = "p1"
            body["quantity"] = 6
            return _case(
                op,
                Technique.BUSINESS_RULE,
                description="Order quantity exceeds available stock",
                steps=[_request(context, op, body=body, expected_status=400)],
                expected_status=400,
                oracle_rules=[oracle],
                metadata={"suite": suite, "rule": rule.get("id", "")},
            )
        if oracle == "order_status_transition":
            create = context.spec.operation("create_order")
            first = _request(
                context,
                create,
                body=_body_for(context, create),
                auth="user",
                expected_status=201,
            )
            first.capture = {"order_id": "body.id"}
            second = _request(
                context,
                op,
                path_overrides={"order_id": "${order_id}"},
                body={"status": "shipped"},
                auth="user",
                expected_status=409,
            )
            return _case(
                op,
                Technique.BUSINESS_RULE,
                description="Illegal pending -> shipped order transition is rejected",
                steps=[first, second],
                expected_status=409,
                oracle_rules=[oracle],
                metadata={"suite": suite, "rule": rule.get("id", "")},
            )
        if oracle == "delete_conflict":
            return _case(
                op,
                Technique.BUSINESS_RULE,
                description="Deleting a product referenced by an order is rejected",
                steps=[
                    _request(
                        context,
                        op,
                        path_overrides={"product_id": "p1"},
                        expected_status=409,
                    )
                ],
                expected_status=409,
                oracle_rules=[oracle],
                metadata={"suite": suite, "rule": rule.get("id", "")},
            )
    return None


def _dedupe(cases: list[TestCase]) -> list[TestCase]:
    seen: set[tuple[str, str]] = set()
    result: list[TestCase] = []
    for case in cases:
        key = (case.operation_id, case.technique.value)
        if key in seen:
            continue
        seen.add(key)
        result.append(case)
    return result


class GeneratorAgent(BaseAgent):
    def run(
        self,
        context: AgentContext,
        plan: TestPlan,
        analysis: SpecAnalysis | None = None,
    ) -> list[TestCase]:
        started = time.perf_counter()
        deterministic = self._deterministic(context, plan, analysis)
        if not context.llm_allowed("generation"):
            context.trace(self.name, "deterministic_generation", f"{len(deterministic)} cases")
            return deterministic
        response = context.gateway.complete(
            "generation",
            {
                "operations": [self._operation_payload(context, item) for item in plan.items],
                "allowed_techniques": [technique.value for technique in Technique],
                "business_rules": context.spec.extensions.get("x-agenticapi-business-rules", []),
                "max_cases": context.config.max_cases_total,
                "timeout_note": "Use only documented methods and paths. Return JSON only.",
            },
        )
        if response.error or not isinstance(response.parsed, dict):
            context.trace(
                self.name,
                "llm_generation_failed",
                response.error or "malformed LLM response",
                started=started,
                provider=response.provider,
                error=response.error,
            )
            if context.allow_fallback:
                return deterministic
            raise LLMGenerationError(f"LLM generation failed: {response.error or 'malformed response'}")
        llm_cases = self._parse_cases(context, response.parsed.get("cases", []))
        if not llm_cases:
            context.trace(
                self.name,
                "llm_generation_empty",
                "no usable LLM cases",
                started=started,
                provider=response.provider,
            )
            if context.allow_fallback:
                return deterministic
            raise LLMGenerationError("LLM generation returned no usable cases")
        if context.allow_fallback:
            covered = {(case.operation_id, case.technique) for case in llm_cases}
            llm_cases.extend(
                case
                for case in deterministic
                if (case.operation_id, case.technique) not in covered
            )
        cases = _dedupe(llm_cases)
        context.trace(
            self.name,
            "llm_generation",
            f"{len(cases)} cases",
            started=started,
            provider=response.provider,
        )
        return cases

    def _deterministic(
        self,
        context: AgentContext,
        plan: TestPlan,
        analysis: SpecAnalysis | None,
    ) -> list[TestCase]:
        suite = context.config.condition_id
        cases: list[TestCase] = []
        for item in plan.items:
            op = context.spec.operation(item.operation_id)
            per_operation: list[TestCase] = []
            for technique in item.techniques:
                case: TestCase | None = None
                if technique is Technique.FUNCTIONAL:
                    case = _functional(context, op, suite)
                elif technique is Technique.NEGATIVE:
                    case = _negative(context, op, suite)
                elif technique is Technique.BOUNDARY:
                    case = _boundary(context, op, suite)
                elif technique is Technique.AUTH:
                    case = _auth(context, op, suite)
                elif technique is Technique.AUTHZ:
                    case = _authz(context, op, suite)
                elif technique is Technique.STATEFUL:
                    case = _stateful(context, op, suite)
                elif technique is Technique.IDEMPOTENCY:
                    case = _idempotency(context, op, suite)
                elif technique is Technique.BUSINESS_RULE:
                    case = _business_rule(context, op, suite)
                if case is not None:
                    per_operation.append(case)
                if len(per_operation) >= item.max_cases:
                    break
            cases.extend(per_operation)
        return _dedupe(cases)

    def _operation_payload(self, context: AgentContext, item: TestPlanItem) -> dict[str, Any]:
        op = context.spec.operation(item.operation_id)
        kept_statuses = {"200", "201", "202", "204", "400", "401", "403", "404", "409", "422"}
        responses = {
            str(code): response.description
            for code, response in op.responses.items()
            if str(code) in kept_statuses
        }
        return {
            "operation_id": op.operation_id,
            "method": op.method,
            "path": op.path,
            "summary": op.summary,
            "auth": op.requires_auth,
            "techniques": [technique.value for technique in item.techniques],
            "parameters": [
                {
                    "name": parameter.name,
                    "location": parameter.location,
                    "required": parameter.required,
                    "schema": parameter.schema,
                }
                for parameter in op.parameters
            ],
            "request_body": {
                "required": op.request_body.required,
                "schema": op.request_body.schema_for(),
            }
            if op.request_body
            else None,
            "success_status": op.success_status,
            "responses": responses,
            "path_examples": {
                parameter.name: {
                    "product_id": "p1",
                    "order_id": "o1",
                    "username": "alice",
                }.get(parameter.name, "example")
                for parameter in op.parameters
                if parameter.location == "path"
            },
        }

    def _parse_cases(self, context: AgentContext, raw_cases: Any) -> list[TestCase]:
        if not isinstance(raw_cases, list):
            return []
        known = context.spec.operation_map()
        cases: list[TestCase] = []
        for raw in raw_cases[: context.config.max_cases_total]:
            if not isinstance(raw, dict):
                continue
            operation_id = str(raw.get("operation_id", ""))
            if operation_id not in known:
                continue
            try:
                technique = Technique(str(raw.get("technique", "")))
            except ValueError:
                continue
            op = known[operation_id]
            default_auth = (
                None
                if technique in {Technique.AUTH, Technique.AUTHZ}
                else (_auth_for(op) if op.requires_auth else None)
            )
            steps = self._parse_steps(
                context, op, raw.get("steps", []), default_auth=default_auth
            )
            if not steps:
                continue
            assertions = [
                Assertion(
                    kind=str(item.get("kind", "")),
                    target=str(item.get("target", "")),
                    expected=item.get("expected"),
                    description=str(item.get("description", "")),
                )
                for item in raw.get("assertions", [])
                if isinstance(item, dict) and item.get("kind")
            ]
            expected = raw.get("expected_status", steps[-1].expected_status)
            expected_int = (
                int(expected)
                if isinstance(expected, int)
                or (isinstance(expected, str) and expected.isdigit())
                else None
            )
            if expected_int is not None and steps[-1].expected_status is None:
                steps[-1].expected_status = expected_int
            case = TestCase(
                case_id=str(raw.get("case_id") or f"{operation_id}__llm_{len(cases) + 1}"),
                operation_id=operation_id,
                technique=technique,
                description=str(raw.get("description", "LLM-generated case")),
                steps=steps,
                assertions=assertions,
                expected_status=expected_int,
                oracle_rules=[str(rule) for rule in raw.get("oracle_rules", []) if isinstance(rule, str)],
                metadata={"generated_by": "llm", "raw": raw},
                generated_by="llm",
            )
            cases.append(case)
        return cases

    def _parse_steps(
        self,
        context: AgentContext,
        op: Operation,
        raw_steps: Any,
        *,
        default_auth: str | None = None,
    ) -> list[RequestStep]:
        if not isinstance(raw_steps, list):
            return []
        steps: list[RequestStep] = []
        for raw in raw_steps[:6]:
            if not isinstance(raw, dict):
                continue
            method = str(raw.get("method", "")).upper()
            path = str(raw.get("path", ""))
            if method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"}:
                continue
            if not path.startswith("/"):
                continue
            body = raw.get("body", _MISSING)
            step = RequestStep(
                method=method,
                path=path,
                path_params=dict(raw.get("path_params", {}) or {}),
                query=dict(raw.get("query", {}) or {}),
                headers={
                    str(key): str(value)
                    for key, value in (raw.get("headers", {}) or {}).items()
                },
                body=None if body is _MISSING else body,
                media_type=str(raw.get("media_type", "application/json")),
                form=dict(raw.get("form", {}) or {}),
                files=dict(raw.get("files", {}) or {}),
                auth=(
                    raw.get("auth")
                    if raw.get("auth") in {"user", "admin"}
                    else default_auth
                ),
                capture={
                    str(key): str(value)
                    for key, value in (raw.get("capture", {}) or {}).items()
                },
                expected_status=raw.get("expected_status") if isinstance(raw.get("expected_status"), int) else None,
                label=str(raw.get("label", op.operation_id)),
            )
            steps.append(step)
        return steps
