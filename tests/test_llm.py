"""Tests for the provider-independent LLM layer."""

from __future__ import annotations

import contextlib
import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast

import jsonschema
import pytest

from agenticapi.config import Settings
from agenticapi.llm import (
    GENERATION_SCHEMA,
    PLANNING_SCHEMA,
    SCHEMAS,
    TASK_PROMPTS,
    DeterministicProvider,
    LLMGateway,
    LLMProvider,
    OllamaProvider,
    OpenAICompatibleProvider,
    ScriptedProvider,
    build_messages,
    get_prompt,
    redact_secrets,
)
from agenticapi.models import LLMUnavailable


class StubServer(ThreadingHTTPServer):
    responses: list[tuple[int, Any]]
    requests: list[dict[str, Any]]


class _StubHandler(BaseHTTPRequestHandler):
    server_version = "StubLLM/1.0"

    def do_POST(self) -> None:
        server = cast(StubServer, self.server)
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        body = json.loads(raw.decode("utf-8"))
        server.requests.append(
            {
                "path": self.path,
                "headers": {key.lower(): value for key, value in self.headers.items()},
                "body": body,
            }
        )
        status, payload = server.responses.pop(0)
        if isinstance(payload, (dict, list)):
            data = json.dumps(payload).encode("utf-8")
            content_type = "application/json"
        else:
            data = str(payload).encode("utf-8")
            content_type = "text/plain"
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: Any) -> None:
        pass


@contextlib.contextmanager
def stub_server(
    responses: list[tuple[int, Any]],
) -> Iterator[StubServer]:
    server = StubServer(("127.0.0.1", 0), _StubHandler)
    server.responses = list(responses)
    server.requests = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def make_settings(root: Path, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "root": root,
        "artifacts_dir": root / "artifacts",
        "datasets_dir": root / "datasets",
        "configs_dir": root / "configs",
        "llm_provider": "openai_compatible",
        "llm_api_key": "test-key",
        "llm_base_url": "http://127.0.0.1:9/v1",
        "llm_model": "stub-model",
        "llm_timeout_seconds": 2.0,
        "llm_max_retries": 2,
        "input_price_per_million": None,
        "output_price_per_million": None,
        "default_base_url": "http://127.0.0.1:8765",
        "default_token": "token-alice",
    }
    values.update(overrides)
    return Settings(**values)


def chat_completion(
    content: str,
    *,
    prompt_tokens: int = 11,
    completion_tokens: int = 7,
    model: str = "stub-model",
) -> dict[str, Any]:
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


VALID_CASE: dict[str, Any] = {
    "case_id": "op_get_pet_boundary_1",
    "operation_id": "get_pet",
    "technique": "boundary",
    "description": "Request a pet with a zero identifier.",
    "steps": [
        {
            "method": "GET",
            "path": "/pets/{petId}",
            "path_params": {"petId": 0},
            "expected_status": 400,
        }
    ],
    "assertions": [
        {"kind": "status", "target": "response.status_code", "expected": 400},
        {"kind": "schema", "target": "body", "expected": "error"},
    ],
    "expected_status": 400,
    "oracle_rules": ["status must be 400", "body must contain an error message"],
}


def test_openai_provider_without_key_raises_and_gateway_reports_unavailable(
    tmp_path: Path,
) -> None:
    settings = make_settings(tmp_path, llm_api_key="")
    provider = OpenAICompatibleProvider(settings)
    with pytest.raises(LLMUnavailable, match="API_KEY"):
        provider.complete([{"role": "user", "content": "hello"}])

    gateway = LLMGateway(provider, settings)
    response = gateway.complete("planning", {"operations": []})
    assert response.error
    assert "unavailable" in response.error.lower()
    assert gateway.calls == 0


@pytest.mark.parametrize("task", sorted(SCHEMAS))
def test_deterministic_provider_returns_schema_valid_fallback(task: str) -> None:
    provider = DeterministicProvider()
    response = provider.complete(
        [{"role": "user", "content": "analyse"}],
        task=task,
        response_schema=SCHEMAS[task],
    )
    assert response.provider == "deterministic"
    assert response.is_llm is False
    assert isinstance(response.parsed, dict)
    jsonschema.validate(instance=response.parsed, schema=SCHEMAS[task])


def test_deterministic_gateway_is_not_llm_and_has_unknown_cost() -> None:
    gateway = LLMGateway(DeterministicProvider())
    response = gateway.complete("generation", {"operations": ["get_pet"]})
    assert response.parsed == {"cases": []}
    assert response.is_llm is False
    assert gateway.is_llm is False
    assert gateway.cost_usd is None
    assert gateway.calls == 1


def test_scripted_provider_returns_parsed_json_and_usage() -> None:
    provider = ScriptedProvider(
        {"planning": {"items": []}},
        prompt_tokens=9,
        completion_tokens=4,
    )
    response = provider.complete(
        [{"role": "user", "content": "plan"}],
        task="planning",
        response_schema=PLANNING_SCHEMA,
    )
    assert response.parsed == {"items": []}
    assert json.loads(response.text) == {"items": []}
    assert response.prompt_tokens == 9
    assert response.completion_tokens == 4
    assert response.total_tokens == 13
    assert response.is_llm is False
    assert provider.received[0]["task"] == "planning"


def test_ollama_provider_sends_response_schema_as_format() -> None:
    with stub_server(
        [
            (
                200,
                {
                    "model": "qwen2.5:1.5b",
                    "message": {"role": "assistant", "content": '{"cases": []}'},
                },
            )
        ]
    ) as server:
        provider = OllamaProvider(
            base_url=f"http://127.0.0.1:{server.server_address[1]}",
            model="qwen2.5:1.5b",
            timeout=5.0,
        )
        response = provider.complete(
            [{"role": "user", "content": "repair"}],
            response_schema=SCHEMAS["repair"],
            task="repair",
        )

        assert response.error == ""
        assert response.text == '{"cases": []}'
        assert len(server.requests) == 1
        request = server.requests[0]
        assert request["path"] == "/api/chat"
        assert request["body"]["format"] == SCHEMAS["repair"]
        assert request["body"]["stream"] is False


def test_openai_provider_against_local_stub_server(tmp_path: Path) -> None:
    content = json.dumps({"cases": []})
    with stub_server(
        [(200, chat_completion(content, prompt_tokens=13, completion_tokens=5))]
    ) as server:
        base_url = f"http://127.0.0.1:{server.server_address[1]}/v1"
        settings = make_settings(tmp_path, llm_base_url=base_url)
        provider = OpenAICompatibleProvider(settings, sleep=lambda _: None)
        response = provider.complete(
            [
                {"role": "system", "content": "be careful"},
                {"role": "user", "content": "generate"},
            ],
            response_schema=GENERATION_SCHEMA,
            task="generation",
        )

        assert response.parsed == {"cases": []}
        assert response.prompt_tokens == 13
        assert response.completion_tokens == 5
        assert response.total_tokens == 18
        assert response.is_llm is True
        assert response.cost_usd is None
        assert len(server.requests) == 1

        request = server.requests[0]
        assert request["path"] == "/v1/chat/completions"
        assert request["headers"]["authorization"] == "Bearer test-key"
        body = request["body"]
        assert body["model"] == "stub-model"
        assert body["temperature"] == 0
        assert body["response_format"] == {"type": "json_object"}
        assert body["messages"] == [
            {"role": "system", "content": "be careful"},
            {"role": "user", "content": "generate"},
        ]


def test_openai_provider_retries_429_then_succeeds(tmp_path: Path) -> None:
    content = json.dumps({"items": []})
    with stub_server(
        [
            (429, {"error": "rate limited"}),
            (200, chat_completion(content)),
        ]
    ) as server:
        base_url = f"http://127.0.0.1:{server.server_address[1]}/v1"
        settings = make_settings(
            tmp_path,
            llm_base_url=base_url,
            llm_max_retries=1,
        )
        provider = OpenAICompatibleProvider(settings, sleep=lambda _: None)
        response = provider.complete(
            [{"role": "user", "content": "plan"}],
            response_schema=PLANNING_SCHEMA,
            task="planning",
        )

        assert response.parsed == {"items": []}
        assert response.is_llm is True
        assert len(server.requests) == 2


def test_gateway_retries_invalid_json_then_reports_clear_error() -> None:
    provider = ScriptedProvider({"generation": "this is not json"})
    gateway = LLMGateway(provider, max_calls=10, max_repairs=2)
    response = gateway.complete("generation", {"operations": ["get_pet"]})

    assert response.parsed is None
    assert "invalid JSON" in response.error
    assert "3 attempt" in response.error
    assert len(provider.received) == 3
    assert gateway.calls == 3
    assert gateway.cost_usd is None

    final_message = provider.received[-1]["messages"][-1]["content"]
    assert "corrected JSON object" in final_message


def test_gateway_schema_validation_rejects_malformed_output() -> None:
    malformed = {
        "cases": [
            {"case_id": "c1", "operation_id": "get_pet", "technique": "chaos"}
        ]
    }
    provider = ScriptedProvider({"generation": malformed})
    gateway = LLMGateway(provider, max_repairs=2)
    response = gateway.complete("generation", {})

    assert response.parsed is None
    assert "schema validation" in response.error
    assert "3 attempt" in response.error
    assert gateway.calls == 3


def test_gateway_accepts_valid_generation_output() -> None:
    provider = ScriptedProvider({"generation": {"cases": [VALID_CASE]}})
    gateway = LLMGateway(provider)
    response = gateway.complete("generation", {})

    assert response.error == ""
    assert response.parsed == {"cases": [VALID_CASE]}
    assert response.is_llm is False
    assert gateway.calls == 1


def test_generation_schema_requires_core_case_fields() -> None:
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            {"cases": [{"operation_id": "get_pet", "technique": "functional"}]},
            GENERATION_SCHEMA,
        )


def test_gateway_cost_is_none_when_prices_are_unset(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    provider = ScriptedProvider(
        {"planning": {"items": []}},
        prompt_tokens=1000,
        completion_tokens=500,
    )
    gateway = LLMGateway(provider, settings)
    response = gateway.complete("planning", {})

    assert response.cost_usd is None
    assert gateway.cost_usd is None
    assert gateway.prompt_tokens == 1000
    assert gateway.completion_tokens == 500


def test_gateway_cost_is_numeric_when_prices_are_set(tmp_path: Path) -> None:
    settings = make_settings(
        tmp_path,
        input_price_per_million=1.0,
        output_price_per_million=2.0,
    )
    provider = ScriptedProvider(
        {"planning": {"items": []}},
        prompt_tokens=1000,
        completion_tokens=500,
    )
    gateway = LLMGateway(provider, settings)
    response = gateway.complete("planning", {})

    expected = 1000 / 1_000_000 * 1.0 + 500 / 1_000_000 * 2.0
    assert response.cost_usd == pytest.approx(expected)
    assert gateway.cost_usd == pytest.approx(expected)


class ExplodingProvider(LLMProvider):
    name = "exploding"
    model = "none"
    is_llm = True

    def complete(
        self,
        messages: Any,
        *,
        response_schema: Any = None,
        task: str = "",
        timeout: float | None = None,
    ) -> Any:
        raise RuntimeError(
            "Authorization: Bearer secret and sk-abcdefghijklmnop"
        )


def test_gateway_redacts_secrets_in_errors() -> None:
    gateway = LLMGateway(ExplodingProvider())
    response = gateway.complete("generation", {})

    assert "[REDACTED]" in response.error
    assert "secret" not in response.error
    assert "sk-abcdefghijklmnop" not in response.error
    assert "secret" not in redact_secrets("Bearer secret")


def test_gateway_enforces_max_calls() -> None:
    provider = ScriptedProvider({"generation": "not json"})
    gateway = LLMGateway(provider, max_calls=1, max_repairs=2)
    response = gateway.complete("generation", {})

    assert gateway.calls == 1
    assert len(provider.received) == 1
    assert "limit" in response.error.lower()


def test_prompt_templates_cover_all_schemas() -> None:
    assert set(TASK_PROMPTS) == set(SCHEMAS)
    messages = build_messages("generation", {"operations": ["get_pet"]})
    assert messages[0]["role"] == "system"
    assert "get_pet" in messages[1]["content"]
    with pytest.raises(KeyError):
        get_prompt("unknown-task")
