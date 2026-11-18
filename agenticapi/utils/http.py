"""Minimal JSON HTTP helpers with loopback enforcement and timeouts."""

from __future__ import annotations

from typing import Any

import requests

from agenticapi.security import assert_local_url, redact


class HTTPError(RuntimeError):
    pass


class JsonClient:
    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        assert_local_url(base_url, allow_path_only=False)
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        json_body: Any = None,
        data: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> requests.Response:
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        assert_local_url(url, allow_path_only=False)
        try:
            return self.session.request(
                method.upper(),
                url,
                params=params,
                headers=headers,
                json=json_body,
                data=data,
                files=files,
                timeout=timeout or self.timeout,
            )
        except requests.RequestException as exc:
            raise HTTPError(redact(str(exc))) from exc

    def json_request(self, method: str, path: str, **kwargs: Any) -> tuple[int, Any]:
        response = self.request(method, path, **kwargs)
        try:
            body = response.json() if response.content else None
        except ValueError:
            body = response.text
        return response.status_code, body

    def close(self) -> None:
        self.session.close()

    def __enter__(self) -> JsonClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
