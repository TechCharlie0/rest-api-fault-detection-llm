"""Fake LLM provider for testing and CI."""

from __future__ import annotations

import json
from typing import Any

from agenticapi.llm.provider import LLMProvider, LLMResponse


class FakeLLMProvider(LLMProvider):
    """Minimal fake provider that returns a fixed payload.

    Used by integration tests when a real LLM API key is not configured.
    """

    name = "fake"
    is_llm = True

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.received: list[dict[str, Any]] = []

    @property
    def configured(self) -> bool:
        return True

    @property
    def model(self) -> str:
        return "fake-model"

    def complete(self, messages, *, response_schema=None, task="", timeout=None) -> LLMResponse:
        self.received.append({"task": task, "messages": list(messages)})
        text = json.dumps(self.payload)
        return LLMResponse(
            provider=self.name,
            model=self.model,
            text=text,
            parsed=self.payload,
            prompt_tokens=10,
            completion_tokens=5,
            is_llm=True,
        )