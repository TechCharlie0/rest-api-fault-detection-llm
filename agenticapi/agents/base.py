"""Shared agent context and tracing."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agenticapi.config import Settings
from agenticapi.llm.gateway import LLMGateway
from agenticapi.models import APISpec, DependencyGraph, ExperimentConfig, TraceEvent


@dataclass
class AgentContext:
    settings: Settings
    spec: APISpec
    graph: DependencyGraph
    config: ExperimentConfig
    artifact_dir: Path
    gateway: LLMGateway
    use_llm: bool = False
    allow_fallback: bool = False
    traces: list[TraceEvent] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def llm_available(self) -> bool:
        return bool(self.use_llm and self.gateway.is_llm and self.gateway.available)

    def llm_allowed(self, role: str) -> bool:
        if not self.llm_available:
            return False
        roles = self.extra.get("llm_roles")
        return roles is None or role in roles

    def trace(
        self,
        agent: str,
        action: str,
        summary: str = "",
        *,
        started: float | None = None,
        provider: str = "",
        error: str = "",
    ) -> None:
        duration = (time.perf_counter() - started) * 1000.0 if started is not None else 0.0
        self.traces.append(
            TraceEvent(
                agent=agent,
                action=action,
                summary=summary[:2000],
                duration_ms=duration,
                provider=provider,
                error=error,
            )
        )


class BaseAgent:
    name = "base"

    def __init__(self) -> None:
        self.name = type(self).__name__.removesuffix("Agent").lower()
