"""Provider-independent LLM access for structured AgenticAPI research tasks."""

from agenticapi.llm.gateway import LLMGateway
from agenticapi.llm.prompts import (
    PROMPTS,
    SYSTEM_PROMPT,
    TASK_PROMPTS,
    build_messages,
    get_prompt,
    render,
    repair_instruction,
)
from agenticapi.llm.provider import (
    DeterministicProvider,
    LLMProvider,
    LLMRequestError,
    OllamaProvider,
    OpenAICompatibleProvider,
    ScriptedProvider,
    redact_secrets,
)
from agenticapi.llm.schemas import (
    GENERATION_SCHEMA,
    PLANNING_SCHEMA,
    REPAIR_SCHEMA,
    SCHEMAS,
    SPEC_ANALYSIS_SCHEMA,
    schema_for,
)

__all__ = [
    "DeterministicProvider",
    "GENERATION_SCHEMA",
    "LLMGateway",
    "LLMProvider",
    "LLMRequestError",
    "OllamaProvider",
    "OpenAICompatibleProvider",
    "PLANNING_SCHEMA",
    "PROMPTS",
    "REPAIR_SCHEMA",
    "SCHEMAS",
    "SPEC_ANALYSIS_SCHEMA",
    "SYSTEM_PROMPT",
    "ScriptedProvider",
    "TASK_PROMPTS",
    "build_messages",
    "get_prompt",
    "redact_secrets",
    "render",
    "repair_instruction",
    "schema_for",
]
