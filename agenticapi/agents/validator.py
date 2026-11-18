"""Validator: reject malformed or undocumented test cases before execution."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from agenticapi.agents.base import AgentContext, BaseAgent
from agenticapi.models import Operation, Technique, TestCase

_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
_ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"}
_KNOWN_RULES = {
    "quantity_le_stock",
    "order_status_transition",
    "delete_conflict",
    "idempotent_create",
}
_ASSERTION_KINDS = {"status", "schema", "json_path", "header", "same_as_step"}


@dataclass
class ValidationReport:
    valid: list[TestCase] = field(default_factory=list)
    invalid: list[tuple[TestCase, list[str]]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def valid_count(self) -> int:
        return len(self.valid)

    @property
    def invalid_count(self) -> int:
        return len(self.invalid)

    def to_dict(self) -> dict[str, object]:
        return {
            "valid": [case.case_id for case in self.valid],
            "invalid": [
                {"case_id": case.case_id, "errors": errors}
                for case, errors in self.invalid
            ],
            "errors": self.errors,
        }


class ValidatorAgent(BaseAgent):
    def run(self, context: AgentContext, cases: list[TestCase]) -> ValidationReport:
        report = ValidationReport()
        seen_ids: set[str] = set()
        for case in cases:
            errors = self._validate_case(context, case)
            if case.case_id in seen_ids:
                errors.append(f"duplicate case_id {case.case_id!r}")
            seen_ids.add(case.case_id)
            if errors:
                report.invalid.append((case, errors))
            else:
                report.valid.append(case)
        context.trace(
            self.name,
            "validation",
            f"{report.valid_count} valid, {report.invalid_count} invalid",
        )
        return report

    def _validate_case(self, context: AgentContext, case: TestCase) -> list[str]:
        errors: list[str] = []
        if not case.case_id or not case.case_id.strip():
            errors.append("case_id is empty")
        if case.operation_id not in context.spec.operation_map():
            return errors + [f"unknown operation_id {case.operation_id!r}"]
        if not isinstance(case.technique, Technique):
            errors.append(f"invalid technique {case.technique!r}")
        if not case.steps:
            return errors + ["case has no steps"]
        if len(case.steps) > 6:
            errors.append("case has more than 6 steps")
        captured: set[str] = set()
        operation = context.spec.operation(case.operation_id)
        for index, step in enumerate(case.steps, start=1):
            if step.method not in _ALLOWED_METHODS:
                errors.append(f"step {index}: unsupported method {step.method!r}")
            if not step.path.startswith("/"):
                errors.append(f"step {index}: path must start with '/'")
            if "://" in step.path:
                errors.append(f"step {index}: absolute URLs are not allowed")
            if not self._documented(context, step.method, step.path):
                errors.append(
                    f"step {index}: {step.method} {step.path} is not documented in the spec"
                )
            for name in _VAR_RE.findall(step.path):
                if name not in captured:
                    errors.append(f"step {index}: path variable {name!r} was not captured earlier")
            for name in step.capture:
                captured.add(name)
            if step.expected_status is not None:
                if not 100 <= step.expected_status <= 599:
                    errors.append(f"step {index}: invalid expected status {step.expected_status}")
            for assertion in case.assertions:
                if assertion.kind not in _ASSERTION_KINDS:
                    errors.append(f"unknown assertion kind {assertion.kind!r}")
        for rule in case.oracle_rules:
            if rule not in _KNOWN_RULES:
                errors.append(f"unknown oracle rule {rule!r}")
        if case.expected_status is None and all(step.expected_status is None for step in case.steps):
            errors.append("case does not declare any expected status")
        if case.operation_id != operation.operation_id:
            errors.append("operation id mismatch")
        return errors

    @staticmethod
    def _documented(context: AgentContext, method: str, path: str) -> bool:
        normalized = _VAR_RE.sub(lambda match: "{" + match.group(1) + "}", path)
        if not normalized.startswith("/"):
            return False
        for op in context.spec.operations:
            if op.method == method.upper() and _path_matches(op.path, normalized):
                return True
        return False


def _path_matches(template: str, candidate: str) -> bool:
    template_parts = template.strip("/").split("/")
    candidate_parts = candidate.strip("/").split("/")
    if len(template_parts) != len(candidate_parts):
        return False
    for expected, actual in zip(template_parts, candidate_parts, strict=False):
        if expected.startswith("{") and expected.endswith("}"):
            if not actual:
                return False
            continue
        if expected != actual:
            return False
    return True


def operation_for_path(context: AgentContext, method: str, path: str) -> Operation | None:
    normalized = _VAR_RE.sub(lambda match: "{" + match.group(1) + "}", path)
    for op in context.spec.operations:
        if op.method == method.upper() and _path_matches(op.path, normalized):
            return op
    return None
