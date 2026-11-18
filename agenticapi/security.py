"""Security helpers: localhost allowlist, secret redaction, and generated-code checks."""

from __future__ import annotations

import ast
import ipaddress
import re
from pathlib import Path
from urllib.parse import urlparse

LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}
ALLOWED_IMPORTS = {
    "__future__",
    "agenticapi",
    "base64",
    "json",
    "jsonschema",
    "os",
    "pytest",
    "requests",
    "time",
    "uuid",
}
FORBIDDEN_CALLS = {
    "eval",
    "exec",
    "compile",
    "open",
    "input",
    "__import__",
    "breakpoint",
}
FORBIDDEN_ATTRS = {
    ("os", "system"),
    ("os", "popen"),
    ("os", "remove"),
    ("os", "unlink"),
    ("os", "rmdir"),
    ("os", "removedirs"),
    ("shutil", "rmtree"),
    ("subprocess", "run"),
    ("subprocess", "Popen"),
    ("subprocess", "call"),
    ("subprocess", "check_output"),
    ("socket", "socket"),
}
SECRET_PATTERNS = [
    re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[A-Za-z0-9._\-]+"),
    re.compile(r"(?i)(api[_-]?key\s*[:=]\s*)[^\s,;'\"]+"),
    re.compile(r"(?i)(token\s*[:=]\s*)[^\s,;'\"]+"),
    re.compile(r"(?i)(password\s*[:=]\s*)[^\s,;'\"]+"),
    re.compile(r"(?i)(secret\s*[:=]\s*)[^\s,;'\"]+"),
    re.compile(r"sk-[A-Za-z0-9_\-]{12,}"),
]


def is_loopback_host(host: str | None) -> bool:
    if not host:
        return False
    normalized = host.strip().strip("[]").lower()
    if normalized in LOOPBACK_HOSTS:
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def assert_local_url(url: str, *, allow_path_only: bool = True) -> None:
    if allow_path_only and url.startswith("/"):
        return
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"unsupported URL scheme: {parsed.scheme!r}")
    if not is_loopback_host(parsed.hostname):
        raise ValueError(f"non-loopback host rejected: {parsed.hostname!r}")


def assert_safe_base_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("base URL must be http or https")
    if not is_loopback_host(parsed.hostname):
        raise ValueError("base URL must resolve to a loopback host")


def redact(text: str) -> str:
    result = text
    for pattern in SECRET_PATTERNS:
        if pattern.groups:
            result = pattern.sub(lambda m: m.group(1) + "[REDACTED]", result)
        else:
            result = pattern.sub("[REDACTED]", result)
    return result


def safe_filename(value: str, *, fallback: str = "case") -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    if not cleaned:
        cleaned = fallback
    if ".." in cleaned or "/" in cleaned or "\\" in cleaned:
        raise ValueError(f"unsafe filename component: {value!r}")
    return cleaned[:120]


def safe_join(base: Path, name: str) -> Path:
    candidate = (base / safe_filename(name)).resolve()
    root = base.resolve()
    if root not in candidate.parents and candidate != root:
        raise ValueError(f"path escapes base directory: {name!r}")
    return candidate


def validate_generated_code(code: str) -> list[str]:
    errors: list[str] = []
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return [f"syntax error: {exc.msg} at line {exc.lineno}"]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root not in ALLOWED_IMPORTS:
                    errors.append(f"import not allowed: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root not in ALLOWED_IMPORTS:
                errors.append(f"import not allowed: {node.module}")
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in FORBIDDEN_CALLS:
                errors.append(f"call not allowed: {func.id}")
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                if (func.value.id, func.attr) in FORBIDDEN_ATTRS:
                    errors.append(f"call not allowed: {func.value.id}.{func.attr}")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if re.match(r"^https?://", node.value):
                try:
                    assert_local_url(node.value, allow_path_only=False)
                except ValueError as exc:
                    errors.append(f"external URL in generated code: {exc}")
    return errors
