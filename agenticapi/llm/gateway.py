"""Gateway around an LLM provider: JSON validation, repair, and accounting."""

from __future__ import annotations

import json
import time
from collections.abc import Mapping, Sequence
from typing import Any

import jsonschema

from agenticapi.config import Settings
from agenticapi.llm.prompts import build_messages, repair_instruction
from agenticapi.llm.provider import LLMProvider, redact_secrets
from agenticapi.llm.schemas import SCHEMAS
from agenticapi.models import LLMResponse


class LLMGateway:
    """Validate structured LLM output and keep per-run cost/usage accounting."""

    def __init__(
        self,
        provider: LLMProvider,
        settings: Settings | None = None,
        *,
        max_calls: int = 60,
        max_repairs: int = 2,
    ) -> None:
        self.provider = provider
        self.settings = settings
        self.max_calls = max(0, int(max_calls))
        self.max_repairs = max(0, int(max_repairs))
        self.calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.cost_usd: float | None = None
        self.latency_ms = 0.0
        self.is_llm = bool(provider.is_llm)
        self._cost_known = True

    @property
    def available(self) -> bool:
        return bool(self.provider.configured)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def complete(
        self,
        task: str,
        payload: Any = None,
        *,
        messages: Sequence[Mapping[str, Any]] | None = None,
        response_schema: Mapping[str, Any] | None = None,
        schema: Mapping[str, Any] | None = None,
        timeout: float | None = None,
    ) -> LLMResponse:
        """Run one structured task, repairing invalid JSON up to two times."""
        started = time.perf_counter()
        target_schema = response_schema if response_schema is not None else schema
        if target_schema is None:
            target_schema = SCHEMAS.get(task)
        conversation = self._conversation(task, payload, messages)
        if not self.available:
            return self._error(
                "LLM provider is unavailable: no API credentials are configured",
                started,
            )

        last_error = ""
        failed_attempts = 0
        while True:
            if self.calls >= self.max_calls:
                detail = f"LLM call limit reached ({self.max_calls})"
                if last_error:
                    detail = f"{detail}; last error: {last_error}"
                return self._error(detail, started)

            self.calls += 1
            call_started = time.perf_counter()
            try:
                response = self.provider.complete(
                    conversation,
                    response_schema=target_schema,
                    task=task,
                    timeout=timeout,
                )
            except Exception as exc:
                return self._error(str(exc), started)

            elapsed_ms = (time.perf_counter() - call_started) * 1000.0
            self.latency_ms += elapsed_ms
            if response.latency_ms <= 0.0:
                response.latency_ms = elapsed_ms
            self._record_usage(response)

            if response.error:
                response.error = redact_secrets(response.error)
                response.is_llm = self.is_llm
                response.cost_usd = self._cost(response)
                return response

            parsed, problem = self._parse(response.text, target_schema)
            if problem is None:
                response.parsed = parsed
                response.error = ""
                response.is_llm = self.is_llm
                response.cost_usd = self._cost(response)
                return response

            failed_attempts += 1
            last_error = problem
            if failed_attempts > self.max_repairs:
                response.parsed = None
                response.error = redact_secrets(
                    f"{problem} after {failed_attempts} attempt(s)"
                )
                response.is_llm = self.is_llm
                response.cost_usd = self._cost(response)
                return response

            conversation = [
                *conversation,
                {"role": "assistant", "content": response.text},
                {
                    "role": "user",
                    "content": repair_instruction(problem, target_schema),
                },
            ]

    @staticmethod
    def _conversation(
        task: str,
        payload: Any,
        messages: Sequence[Mapping[str, Any]] | None,
    ) -> list[dict[str, Any]]:
        if messages is not None:
            return [dict(message) for message in messages]
        return build_messages(task, payload)

    @staticmethod
    def _parse(
        text: str,
        response_schema: Mapping[str, Any] | None,
    ) -> tuple[Any, str | None]:
        if not isinstance(text, str) or not text.strip():
            return None, "LLM returned an empty response"
        try:
            parsed = json.loads(text)
        except (TypeError, ValueError) as exc:
            return None, f"LLM returned invalid JSON: {exc}"
        if response_schema is not None:
            try:
                jsonschema.validate(instance=parsed, schema=response_schema)
            except jsonschema.ValidationError as exc:
                location = ".".join(str(part) for part in exc.absolute_path)
                location = location or "<root>"
                return None, (
                    f"LLM output failed JSON schema validation at {location}: "
                    f"{exc.message}"
                )
            except jsonschema.SchemaError as exc:
                return None, f"internal response schema error: {exc.message}"
        return parsed, None

    def _record_usage(self, response: LLMResponse) -> None:
        self.prompt_tokens += max(0, int(response.prompt_tokens))
        self.completion_tokens += max(0, int(response.completion_tokens))
        cost = self._cost(response)
        if cost is None:
            self._cost_known = False
            self.cost_usd = None
        elif self._cost_known:
            self.cost_usd = (self.cost_usd or 0.0) + cost

    def _cost(self, response: LLMResponse) -> float | None:
        if self.settings is not None:
            return self.settings.estimate_cost(
                response.prompt_tokens,
                response.completion_tokens,
            )
        return response.cost_usd

    def _error(self, message: str, started: float) -> LLMResponse:
        return LLMResponse(
            provider=self.provider.name,
            model=self.provider.model,
            error=redact_secrets(message),
            latency_ms=(time.perf_counter() - started) * 1000.0,
            is_llm=self.is_llm,
        )
