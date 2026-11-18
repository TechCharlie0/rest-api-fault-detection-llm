"""Spec-derived oracle for status, schema, and declared business rules.

The implementation is separate from the generator, but it shares the same OpenAPI
specification and case expectations, so it is not an independent oracle.
"""

from __future__ import annotations

import time

from agenticapi.agents.base import AgentContext, BaseAgent
from agenticapi.execution.executor import ExecutionRecord, StepExecution
from agenticapi.models import Operation, OracleResult, Outcome, Technique, TestCase
from agenticapi.spec.schema import validate_body


def _status_ok(
    actual: int,
    expected: int | None,
    technique: Technique,
    mode: str,
) -> bool:
    if mode == "legacy":
        return actual < 500
    if expected is None:
        return 200 <= actual < 300
    if actual == expected:
        return True
    if technique is Technique.AUTH and expected in {401, 403} and actual in {401, 403}:
        return True
    if technique in {Technique.NEGATIVE, Technique.BOUNDARY} and expected == 400 and actual == 422:
        return True
    return False


class OracleAgent(BaseAgent):
    def evaluate(
        self,
        context: AgentContext,
        case: TestCase,
        record: ExecutionRecord,
        *,
        mode: str = "full",
    ) -> OracleResult:
        started = time.perf_counter()
        messages: list[str] = []
        step_results: list[dict[str, object]] = []
        if not case.steps:
            return OracleResult(
                case_id=case.case_id,
                outcome=Outcome.INVALID_TEST,
                failure_kind="empty_case",
                messages=["test case has no request steps"],
            )
        if record.error and not record.steps:
            return OracleResult(
                case_id=case.case_id,
                outcome=Outcome.ERROR,
                failure_kind="execution",
                messages=[record.error],
                step_results=[],
            )
        operation = context.spec.operation(case.operation_id)
        failure_kind = ""
        for step, step_planned in zip(record.steps, case.steps, strict=False):
            step_results.append(
                {
                    "index": step.index,
                    "status_code": step.status_code,
                    "expected_status": step_planned.expected_status,
                    "error": step.error,
                }
            )
            if step.error:
                failure_kind = "execution"
                messages.append(f"step {step.index}: {step.error}")
                break
            if step.status_code is None:
                failure_kind = "execution"
                messages.append(f"step {step.index}: no HTTP response")
                break
            if not _status_ok(
                step.status_code,
                step_planned.expected_status,
                case.technique,
                mode,
            ):
                failure_kind = "status"
                messages.append(
                    f"step {step.index}: expected HTTP {step_planned.expected_status}, "
                    f"got {step.status_code}"
                )
                break
            if mode in {"schema", "full"}:
                schema_messages = self._schema_messages(operation, step, context.spec.raw_schemas)
                if schema_messages:
                    failure_kind = "schema"
                    messages.extend(schema_messages)
                    break
        if not failure_kind and mode == "full":
            rule_failure = self._rule_check(case, record)
            if rule_failure:
                failure_kind = "business_rule"
                messages.append(rule_failure)
        outcome = Outcome.PASS if not failure_kind else Outcome.FAIL
        return OracleResult(
            case_id=case.case_id,
            outcome=outcome,
            failure_kind=failure_kind,
            messages=messages,
            step_results=step_results,
            latency_ms=(time.perf_counter() - started) * 1000.0,
        )

    def _schema_messages(
        self,
        operation: Operation,
        step: StepExecution,
        schemas: dict[str, object],
    ) -> list[str]:
        if step.status_code is None:
            return []
        if step.status_code == 204 or step.body is None:
            return []
        response_spec = operation.responses.get(str(step.status_code))
        if response_spec is None:
            return []
        schema = response_spec.schema_for()
        if not schema:
            return []
        errors = validate_body(step.body, schema, schemas)
        if not errors:
            return []
        return [
            f"step {step.index}: response does not match the declared schema: {error}"
            for error in errors[:5]
        ]

    @staticmethod
    def _rule_check(case: TestCase, record: ExecutionRecord) -> str:
        if "idempotent_create" not in case.oracle_rules:
            return ""
        if len(record.steps) < 2:
            return "idempotency check needs two steps"
        first, second = record.steps[0], record.steps[1]
        first_id = first.body.get("id") if isinstance(first.body, dict) else None
        second_id = second.body.get("id") if isinstance(second.body, dict) else None
        if first_id is None or second_id is None:
            return "idempotent response did not contain an id"
        if first_id != second_id:
            return f"idempotency violated: first id {first_id!r}, second id {second_id!r}"
        if first.status_code != second.status_code:
            return "idempotency violated: response status changed between retries"
        return ""
