"""Deterministic HTTP execution of test cases against the local mock API."""

from __future__ import annotations

import base64
import copy
import re
import time
from dataclasses import dataclass, field
from typing import Any

import requests

from agenticapi.models import TestCase
from agenticapi.spec.schema import MISSING, get_path

_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
AUTH_TOKENS = {"user": "token-alice", "admin": "token-admin"}


@dataclass
class StepExecution:
    index: int
    method: str
    path: str
    status_code: int | None = None
    body: Any = None
    text: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    duration_ms: float = 0.0
    error: str = ""
    captures: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "method": self.method,
            "path": self.path,
            "status_code": self.status_code,
            "body": self.body,
            "headers": self.headers,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "captures": self.captures,
        }


@dataclass
class ExecutionRecord:
    case_id: str
    steps: list[StepExecution] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "steps": [step.to_dict() for step in self.steps],
            "error": self.error,
        }


def _substitute(value: Any, captures: dict[str, Any]) -> Any:
    if isinstance(value, str):
        return _VAR_RE.sub(lambda match: str(captures.get(match.group(1), match.group(0))), value)
    if isinstance(value, list):
        return [_substitute(item, captures) for item in value]
    if isinstance(value, dict):
        return {key: _substitute(item, captures) for key, item in value.items()}
    return value


class ExecutionEngine:
    """Execute cases sequentially; reset mock state before each case."""

    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        if not base_url.startswith(("http://127.0.0.1", "http://localhost", "http://[::1]")):
            raise ValueError("execution engine only supports loopback mock APIs")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def reset(self) -> None:
        response = requests.post(f"{self.base_url}/__admin/reset", timeout=self.timeout)
        response.raise_for_status()

    def set_fault(self, fault_id: str | None) -> None:
        response = requests.post(
            f"{self.base_url}/__admin/fault",
            json={"fault_id": fault_id},
            timeout=self.timeout,
        )
        response.raise_for_status()

    def execute(self, case: TestCase) -> ExecutionRecord:
        record = ExecutionRecord(case_id=case.case_id)
        try:
            self.reset()
        except Exception as exc:  # noqa: BLE001
            record.error = f"mock reset failed: {exc}"
            return record
        captures: dict[str, Any] = {}
        for index, step in enumerate(case.steps, start=1):
            started = time.perf_counter()
            path = str(_substitute(step.path, captures))
            path_params = _substitute(step.path_params, captures)
            for name, value in (path_params or {}).items():
                path = path.replace("{" + str(name) + "}", str(value))
            query = _substitute(step.query, captures)
            headers = {
                str(key): str(value)
                for key, value in _substitute(step.headers, captures).items()
            }
            body = _substitute(step.body, captures)
            form = _substitute(step.form, captures)
            files = _files(step.files, captures)
            token = AUTH_TOKENS.get(str(step.auth)) if step.auth else None
            if token:
                headers.setdefault("Authorization", f"Bearer {token}")
            result = StepExecution(
                index=index,
                method=step.method,
                path=path,
            )
            try:
                response = self._request(
                    step.method,
                    path,
                    query=query,
                    headers=headers,
                    body=body,
                    form=form,
                    files=files,
                    media_type=step.media_type,
                )
                result.status_code = response.status_code
                result.duration_ms = (time.perf_counter() - started) * 1000.0
                result.headers = {
                    "content-type": response.headers.get("Content-Type", ""),
                }
                result.text = response.text[:4000]
                try:
                    result.body = response.json() if response.text else None
                except ValueError:
                    result.body = None
                for name, path_expr in step.capture.items():
                    expression = path_expr[5:] if path_expr.startswith("body.") else path_expr
                    value = get_path(result.body, expression)
                    if value is MISSING:
                        result.error = f"capture {name!r} could not read {path_expr!r}"
                        break
                    if isinstance(value, dict):
                        value = value.get("id")
                    captures[name] = value
                    result.captures[name] = value
            except Exception as exc:  # noqa: BLE001
                result.duration_ms = (time.perf_counter() - started) * 1000.0
                result.error = f"{type(exc).__name__}: {exc}"
                record.steps.append(result)
                record.error = result.error
                break
            record.steps.append(result)
            if result.error:
                record.error = result.error
                break
        return record

    def _request(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any],
        headers: dict[str, str],
        body: Any,
        form: dict[str, Any],
        files: dict[str, Any],
        media_type: str,
    ) -> requests.Response:
        url = f"{self.base_url}{path if path.startswith('/') else '/' + path}"
        kwargs: dict[str, Any] = {
            "headers": headers,
            "params": query,
            "timeout": self.timeout,
        }
        if files:
            kwargs["files"] = files
            if form:
                kwargs["data"] = form
        elif form:
            kwargs["data"] = form
        elif body is not None:
            kwargs["json"] = copy.deepcopy(body)
        kwargs["allow_redirects"] = False
        return requests.request(method, url, **kwargs)


def _files(raw: dict[str, Any], captures: dict[str, Any]) -> dict[str, Any]:
    if not raw:
        return {}
    result: dict[str, Any] = {}
    for name, spec in _substitute(raw, captures).items():
        if isinstance(spec, dict):
            filename = str(spec.get("filename", "sample.bin"))
            content = spec.get("content", "")
            content_type = str(spec.get("content_type", "application/octet-stream"))
            try:
                payload = base64.b64decode(content)
            except Exception:  # noqa: BLE001
                payload = str(content).encode("utf-8")
            result[str(name)] = (filename, payload, content_type)
        else:
            result[str(name)] = (str(name), str(spec).encode("utf-8"))
    return result
