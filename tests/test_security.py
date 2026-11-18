"""Security helper tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from agenticapi.agents.code_renderer import render_case
from agenticapi.models import Assertion, RequestStep, Technique, TestCase
from agenticapi.security import (
    assert_local_url,
    assert_safe_base_url,
    is_loopback_host,
    redact,
    safe_filename,
    safe_join,
    validate_generated_code,
)


def test_loopback_allowlist():
    assert is_loopback_host("127.0.0.1")
    assert is_loopback_host("localhost")
    assert is_loopback_host("::1")
    assert not is_loopback_host("example.com")
    assert_local_url("http://127.0.0.1:8000/health")
    with pytest.raises(ValueError):
        assert_local_url("https://example.com/health")
    with pytest.raises(ValueError):
        assert_safe_base_url("http://example.com")


def test_redact_secrets():
    text = "Authorization: Bearer abc.def.ghi api_key=sk-secret-token"
    cleaned = redact(text)
    assert "abc.def.ghi" not in cleaned
    assert "sk-secret-token" not in cleaned
    assert "[REDACTED]" in cleaned


def test_safe_paths(tmp_path: Path):
    assert safe_filename("../../etc/passwd") == "etc_passwd"
    assert safe_filename("..") == "case"
    target = safe_join(tmp_path, "case.py")
    assert target.parent == tmp_path.resolve()


def test_generated_code_policy(tmp_path: Path):
    case = TestCase(
        case_id="x",
        operation_id="health",
        technique=Technique.FUNCTIONAL,
        steps=[RequestStep(method="GET", path="/health", expected_status=200)],
        assertions=[Assertion(kind="status", expected=200)],
        expected_status=200,
    )
    code = render_case(case)
    assert validate_generated_code(code) == []
    bad = "import subprocess\nsubprocess.run(['ls'])\n"
    errors = validate_generated_code(bad)
    assert any("subprocess" in error for error in errors)
    external = "URL = 'https://example.com'\n"
    assert any("external URL" in error for error in validate_generated_code(external))
