"""JSON round-trip helpers for test cases."""

from __future__ import annotations

from typing import Any

from agenticapi.models import Assertion, RequestStep, Technique, TestCase, jsonable


def case_to_dict(case: TestCase) -> dict[str, Any]:
    return jsonable(case)


def case_from_dict(data: dict[str, Any]) -> TestCase:
    steps = [
        RequestStep(
            method=str(step.get("method", "GET")),
            path=str(step.get("path", "/")),
            path_params=dict(step.get("path_params", {}) or {}),
            query=dict(step.get("query", {}) or {}),
            headers={str(k): str(v) for k, v in (step.get("headers", {}) or {}).items()},
            body=step.get("body"),
            media_type=str(step.get("media_type", "application/json")),
            form=dict(step.get("form", {}) or {}),
            files=dict(step.get("files", {}) or {}),
            auth=step.get("auth"),
            capture={str(k): str(v) for k, v in (step.get("capture", {}) or {}).items()},
            expected_status=step.get("expected_status"),
            label=str(step.get("label", "")),
        )
        for step in data.get("steps", [])
    ]
    assertions = [
        Assertion(
            kind=str(item.get("kind", "")),
            target=str(item.get("target", "")),
            expected=item.get("expected"),
            description=str(item.get("description", "")),
        )
        for item in data.get("assertions", [])
    ]
    return TestCase(
        case_id=str(data["case_id"]),
        operation_id=str(data["operation_id"]),
        technique=Technique(str(data["technique"])),
        description=str(data.get("description", "")),
        steps=steps,
        assertions=assertions,
        expected_status=data.get("expected_status"),
        oracle_rules=[str(rule) for rule in data.get("oracle_rules", [])],
        metadata=dict(data.get("metadata", {}) or {}),
        generated_by=str(data.get("generated_by", "deterministic")),
    )
