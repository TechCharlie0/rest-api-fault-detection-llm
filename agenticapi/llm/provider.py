"""Provider abstractions for LLM-backed structured generation.

Providers are deliberately thin: they send messages, return an
:class:`agenticapi.models.LLMResponse`, and never validate JSON themselves.
Validation, repair retries, accounting, and redaction live in the gateway.
"""

from __future__ import annotations

import json
import re
import time
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import requests

from agenticapi.config import Settings
from agenticapi.models import LLMResponse, LLMUnavailable
from agenticapi.security import redact

Message = Mapping[str, Any]
_BEARER_TOKEN = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]+")


def redact_secrets(text: str) -> str:
    """Redact credential shapes, including bare ``Bearer`` tokens."""
    return _BEARER_TOKEN.sub("Bearer [REDACTED]", redact(text))


class LLMRequestError(RuntimeError):
    """Raised when a provider request cannot be completed."""


class LLMProvider(ABC):
    """Provider-independent completion interface."""

    name: str = "abstract"
    is_llm: bool = False

    @property
    def configured(self) -> bool:
        return True

    @property
    def model(self) -> str:
        return ""

    @abstractmethod
    def complete(
        self,
        messages: Sequence[Message],
        *,
        response_schema: Mapping[str, Any] | None = None,
        task: str = "",
        timeout: float | None = None,
    ) -> LLMResponse:
        """Return one completion for ``messages``."""


def _token_count(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


class OpenAICompatibleProvider(LLMProvider):
    """Chat-completions client for OpenAI-compatible HTTP endpoints."""

    name = "openai_compatible"
    is_llm = True

    def __init__(
        self,
        settings: Settings,
        *,
        sleep: Callable[[float], None] | None = None,
        base_delay: float = 0.5,
        max_delay: float = 8.0,
    ) -> None:
        self.settings = settings
        self._sleep = sleep or time.sleep
        self._base_delay = max(0.0, float(base_delay))
        self._max_delay = max(self._base_delay, float(max_delay))

    @property
    def configured(self) -> bool:
        return bool(self.settings.llm_configured)

    @property
    def model(self) -> str:
        return self.settings.llm_model

    @property
    def endpoint(self) -> str:
        base_url = self.settings.llm_base_url.rstrip("/")
        return f"{base_url}/chat/completions"

    def complete(
        self,
        messages: Sequence[Message],
        *,
        response_schema: Mapping[str, Any] | None = None,
        task: str = "",
        timeout: float | None = None,
    ) -> LLMResponse:
        if not self.configured:
            raise LLMUnavailable(
                "LLM is unavailable: AGENTICAPI_LLM_API_KEY is not configured"
            )
        body = self._request_body(messages, response_schema)
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.settings.llm_api_key}",
        }
        started = time.perf_counter()
        response = self._post_with_retries(body, headers, timeout)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        data = self._decode(response)
        content = self._content(data)
        prompt_tokens, completion_tokens = self._usage(data)
        parsed: Any = None
        if response_schema is not None:
            try:
                parsed = json.loads(content)
            except (TypeError, ValueError):
                parsed = None
        cost = self.settings.estimate_cost(prompt_tokens, completion_tokens)
        return LLMResponse(
            provider=self.name,
            model=str(data.get("model") or self.settings.llm_model),
            text=content,
            parsed=parsed,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost,
            latency_ms=elapsed_ms,
            is_llm=True,
            raw=data,
        )

    def _request_body(
        self,
        messages: Sequence[Message],
        response_schema: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.settings.llm_model,
            "messages": [dict(message) for message in messages],
            "temperature": 0,
        }
        if response_schema is not None:
            body["response_format"] = {"type": "json_object"}
        return body

    def _post_with_retries(
        self,
        body: Mapping[str, Any],
        headers: Mapping[str, str],
        timeout: float | None,
    ) -> requests.Response:
        timeout_value = (
            timeout if timeout is not None else self.settings.llm_timeout_seconds
        )
        attempts = max(0, int(self.settings.llm_max_retries)) + 1
        last_status = 0
        last_detail = ""
        for attempt in range(attempts):
            try:
                response = requests.post(
                    self.endpoint,
                    json=dict(body),
                    headers=dict(headers),
                    timeout=timeout_value,
                )
            except requests.RequestException as exc:
                raise LLMRequestError(
                    redact_secrets(f"LLM request failed: {exc}")
                ) from exc
            if response.status_code == 429 or 500 <= response.status_code < 600:
                last_status = response.status_code
                last_detail = self._snippet(response)
                if attempt + 1 < attempts:
                    delay = min(
                        self._base_delay * (2**attempt),
                        self._max_delay,
                    )
                    if delay > 0:
                        self._sleep(delay)
                    continue
                break
            if response.status_code >= 400:
                raise LLMRequestError(
                    redact_secrets(
                        f"LLM request failed with HTTP {response.status_code}: "
                        f"{self._snippet(response)}"
                    )
                )
            return response
        raise LLMRequestError(
            redact_secrets(
                f"LLM request failed after {attempts} attempt(s) with HTTP "
                f"{last_status}: {last_detail}"
            )
        )

    @staticmethod
    def _snippet(response: requests.Response, limit: int = 300) -> str:
        text = " ".join(response.text.split())
        return text[:limit]

    @staticmethod
    def _decode(response: requests.Response) -> dict[str, Any]:
        try:
            data = response.json()
        except ValueError as exc:
            raise LLMRequestError(
                redact_secrets(f"LLM response was not valid JSON: {exc}")
            ) from exc
        if not isinstance(data, dict):
            raise LLMRequestError("LLM response JSON was not an object")
        return data

    @staticmethod
    def _content(data: Mapping[str, Any]) -> str:
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise LLMRequestError("LLM response did not contain any choices")
        first = choices[0]
        if not isinstance(first, dict):
            raise LLMRequestError("LLM response choice was malformed")
        message = first.get("message")
        if not isinstance(message, dict):
            raise LLMRequestError("LLM response message was missing")
        content = message.get("content")
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        return json.dumps(content, sort_keys=True)

    @staticmethod
    def _usage(data: Mapping[str, Any]) -> tuple[int, int]:
        usage = data.get("usage")
        if not isinstance(usage, dict):
            return 0, 0
        prompt = _token_count(usage.get("prompt_tokens", usage.get("input_tokens")))
        completion = _token_count(
            usage.get("completion_tokens", usage.get("output_tokens"))
        )
        return prompt, completion


class ScriptedProvider(LLMProvider):
    """Deterministic test double mapping task names to canned responses."""

    name = "scripted"
    is_llm = False

    def __init__(
        self,
        responses: Mapping[str, Any] | None = None,
        *,
        default_response: Any = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        model: str = "scripted",
    ) -> None:
        self.responses = dict(responses or {})
        self.default_response = {} if default_response is None else default_response
        self.prompt_tokens = _token_count(prompt_tokens)
        self.completion_tokens = _token_count(completion_tokens)
        self._model = model
        self.received: list[dict[str, Any]] = []

    @property
    def model(self) -> str:
        return self._model

    def complete(
        self,
        messages: Sequence[Message],
        *,
        response_schema: Mapping[str, Any] | None = None,
        task: str = "",
        timeout: float | None = None,
    ) -> LLMResponse:
        self.received.append(
            {"task": task, "messages": [dict(message) for message in messages]}
        )
        value = self.responses.get(task, self.default_response)
        if callable(value):
            value = value(messages)
        text = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
        parsed: Any = None
        try:
            parsed = json.loads(text)
        except (TypeError, ValueError):
            parsed = None
        return LLMResponse(
            provider=self.name,
            model=self.model,
            text=text,
            parsed=parsed,
            prompt_tokens=self.prompt_tokens,
            completion_tokens=self.completion_tokens,
            cost_usd=None,
            latency_ms=0.0,
            is_llm=False,
            raw={"task": task},
        )


_DETERMINISTIC_RESPONSES: dict[str, dict[str, Any]] = {
    "spec_analysis": {
        "summary": "Deterministic fallback: no LLM analysis was performed.",
        "operations": [],
        "risk_areas": [],
        "auth_notes": [],
        "notes": [],
    },
    "planning": {"items": []},
    "generation": {"cases": []},
    "repair": {"cases": [], "notes": []},
}


class DeterministicProvider(LLMProvider):
    """No-network fallback.  This is not an LLM and never presents itself as one."""

    name = "deterministic"
    is_llm = False

    @property
    def model(self) -> str:
        return "deterministic"

    def __init__(self) -> None:
        self.received: list[dict[str, Any]] = []

    def complete(
        self,
        messages: Sequence[Message],
        *,
        response_schema: Mapping[str, Any] | None = None,
        task: str = "",
        timeout: float | None = None,
    ) -> LLMResponse:
        self.received.append(
            {"task": task, "messages": [dict(message) for message in messages]}
        )
        value = _DETERMINISTIC_RESPONSES.get(task, {})
        text = json.dumps(value, sort_keys=True)
        return LLMResponse(
            provider=self.name,
            model=self.model,
            text=text,
            parsed=json.loads(text),
            prompt_tokens=0,
            completion_tokens=0,
            cost_usd=None,
            latency_ms=0.0,
            is_llm=False,
            raw={"task": task, "deterministic": True},
        )

# ------------------------------------------------------------------
# Ollama provider
# ------------------------------------------------------------------


class OllamaProvider(LLMProvider):
    """Provider that talks to a local Ollama server via its HTTP API.

    Default endpoint: http://localhost:11434
    Configuration via environment variables:

    - :envvar:`AGENTICAPI_LLM_PROVIDER` → ``ollama``
    - :envvar:`AGENTICAPI_LLM_BASE_URL` → ``http://localhost:11434``
    - :envvar:`AGENTICAPI_LLM_MODEL`   → model name (required)
    - :envvar:`AGENTICAPI_LLM_API_KEY` → ``ollama`` (placeholder, not a real credential)

    The ``AGENTICAPI_LLM_API_KEY`` value is a local compatibility placeholder;
    Ollama does not use bearer authentication.

    .. note::
        This provider does not send requests to cloud providers and does not
        require paid API keys. It is intended for local Ollama installations
        only.
    """

    name = "ollama"
    is_llm = True

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str | None = None,
        timeout: float = 30.0,
        *,
        temperature: float = 0.0,
        seed: int | None = None,
        num_predict: int | None = None,
        num_ctx: int | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._model = model or ""
        self.timeout = timeout
        self.temperature = float(temperature)
        self.seed = seed
        self.num_predict = num_predict
        self.num_ctx = num_ctx

    @property
    def configured(self) -> bool:
        return bool(self._model)

    @property
    def model(self) -> str:
        return self._model

    @property
    def endpoint(self) -> str:
        return f"{self.base_url}/api/chat"

    def complete(
        self,
        messages: Sequence[Mapping[str, Any]],
        *,
        response_schema: Mapping[str, Any] | None = None,
        task: str = "",
        timeout: float | None = None,
    ) -> LLMResponse:
        """Chat completion against a local Ollama instance.

        Parameters
        ----------
        messages : sequence of message dicts
            Each dict should have ``role`` (``"system"``, ``"user"``,
            ``"assistant"``) and ``content`` keys.
        task : str
            Optional task description (informational only).
        timeout : float | None
            Override the default timeout (seconds).

        Returns
        -------
        LLMResponse
            The model's reply, with latency, token counts (when available),
            and the model name.
        """
        to = timeout if timeout is not None else self.timeout
        options: dict[str, Any] = {"temperature": self.temperature}
        if self.seed is not None:
            options["seed"] = self.seed
        if self.num_predict is not None:
            options["num_predict"] = self.num_predict
        if self.num_ctx is not None:
            options["num_ctx"] = self.num_ctx
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [dict(m) for m in messages],
            "stream": False,
            "options": options,
        }
        if response_schema is not None:
            payload["format"] = dict(response_schema)

        started = time.perf_counter()
        try:
            resp = requests.post(
                self.endpoint,
                json=payload,
                timeout=to,
            )
        except requests.RequestException as exc:
            latency_ms = (time.perf_counter() - started) * 1000.0
            return LLMResponse(
                provider=self.name,
                model=self._model,
                text="",
                latency_ms=latency_ms,
                is_llm=True,
                error=f"Ollama request failed: {exc}",
            )

        if resp.status_code != 200:
            return LLMResponse(
                provider=self.name,
                model=self._model,
                text="",
                latency_ms=(time.perf_counter() - started) * 1000.0,
                is_llm=True,
                error=f"Ollama returned HTTP {resp.status_code}",
            )

        try:
            data = resp.json()
        except ValueError:
            return LLMResponse(
                provider=self.name,
                model=self._model,
                text="",
                latency_ms=(time.perf_counter() - started) * 1000.0,
                is_llm=True,
                error="Ollama response was not valid JSON",
            )

        # Extract the assistant message
        message = data.get("message")
        if not isinstance(message, dict):
            return LLMResponse(
                provider=self.name,
                model=self._model,
                text="",
                latency_ms=(time.perf_counter() - started) * 1000.0,
                is_llm=True,
                error="Ollama response did not contain a message object",
            )

        content = message.get("content", "")
        if not isinstance(content, str):
            return LLMResponse(
                provider=self.name,
                model=self._model,
                text="",
                latency_ms=(time.perf_counter() - started) * 1000.0,
                is_llm=True,
                error="Ollama message content is not a string",
            )

        # Ollama reports token counts at the top level; keep a usage fallback
        # for proxy servers that wrap an Ollama response.
        prompt_tokens = _token_count(data.get("prompt_eval_count"))
        completion_tokens = _token_count(data.get("eval_count"))
        usage = data.get("usage")
        if isinstance(usage, dict) and not (prompt_tokens or completion_tokens):
            prompt_tokens = _token_count(
                usage.get("prompt_tokens", usage.get("prompt_eval_count"))
            )
            completion_tokens = _token_count(
                usage.get("completion_tokens", usage.get("eval_count"))
            )

        # Model name from response
        model_from_resp = data.get("model", self._model)

        return LLMResponse(
            provider=self.name,
            model=str(model_from_resp),
            text=content,
            latency_ms=(time.perf_counter() - started) * 1000.0,
            is_llm=True,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )


def build_provider(settings: Settings, *, seed: int | None = None) -> LLMProvider:
    """Build the configured provider without requiring cloud credentials.

    Ollama is selected explicitly via ``AGENTICAPI_LLM_PROVIDER=ollama``;
    all other values retain the OpenAI-compatible behaviour.  Deterministic
    conditions never call this helper.
    """
    provider = (settings.llm_provider or "").strip().lower()
    if provider == "ollama":
        base_url = settings.llm_base_url.rstrip("/")
        if base_url == "https://api.openai.com/v1":
            base_url = "http://localhost:11434"
        return OllamaProvider(
            base_url=base_url,
            model=settings.llm_model,
            timeout=settings.llm_timeout_seconds,
            temperature=settings.llm_temperature,
            seed=seed,
            num_predict=settings.llm_num_predict,
            num_ctx=settings.llm_num_ctx,
        )
    return OpenAICompatibleProvider(settings)
