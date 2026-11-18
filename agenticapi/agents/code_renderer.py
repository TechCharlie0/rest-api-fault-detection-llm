"""Render validated cases as standalone pytest artifacts."""

from __future__ import annotations

import json
import re
from pathlib import Path

from agenticapi.execution.serialization import case_to_dict
from agenticapi.models import GeneratedTest, TestCase
from agenticapi.security import validate_generated_code


def _safe_name(value: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._") or "case"
    return name[:100]


def render_case(case: TestCase, oracle_mode: str = "full") -> str:
    payload = json.dumps(case_to_dict(case), indent=2, sort_keys=True)
    function_name = "test_" + _safe_name(case.case_id).lower()
    return f'''"""Generated AgenticAPI test: {case.case_id}."""

from __future__ import annotations

import os

from agenticapi.execution.executor import ExecutionEngine
from agenticapi.execution.serialization import case_from_dict

CASE = case_from_dict({payload})

def {function_name}() -> None:
    base_url = os.environ.get("AGENTICAPI_BASE_URL", "http://127.0.0.1:8000")
    record = ExecutionEngine(base_url).execute(CASE)
    assert not record.error, record.error
    assert len(record.steps) == len(CASE.steps)
    for observed, planned in zip(record.steps, CASE.steps):
        assert observed.status_code is not None, observed.error
        if planned.expected_status is not None:
            assert observed.status_code == planned.expected_status, (
                f"step {{observed.index}}: expected {{planned.expected_status}}, "
                f"got {{observed.status_code}}"
            )
'''


def write_case(case: TestCase, directory: Path, oracle_mode: str = "full") -> GeneratedTest:
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"{_safe_name(case.case_id)}.py"
    path = directory / filename
    code = render_case(case, oracle_mode)
    path.write_text(code, encoding="utf-8")
    errors = validate_generated_code(code)
    return GeneratedTest(
        case_id=case.case_id,
        file_path=str(path),
        code=code,
        valid=not errors,
        errors=errors,
    )
