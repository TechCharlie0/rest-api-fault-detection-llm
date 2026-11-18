"""Shared fixtures for AgenticAPI tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from agenticapi.agents.base import AgentContext
from agenticapi.config import Settings
from agenticapi.llm.gateway import LLMGateway
from agenticapi.llm.provider import DeterministicProvider
from agenticapi.mock_api.server import MockAPIServer
from agenticapi.models import ExperimentConfig
from agenticapi.spec.graph import build_dependency_graph
from agenticapi.spec.loader import load_spec

ROOT = Path(__file__).resolve().parents[1]


def make_settings(root: Path, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "root": root,
        "artifacts_dir": root / "artifacts",
        "datasets_dir": root / "datasets",
        "configs_dir": root / "configs",
        "llm_provider": "openai_compatible",
        "llm_api_key": "",
        "llm_base_url": "http://127.0.0.1:9/v1",
        "llm_model": "stub-model",
        "llm_timeout_seconds": 2.0,
        "llm_max_retries": 1,
        "input_price_per_million": None,
        "output_price_per_million": None,
        "default_base_url": "http://127.0.0.1:8765",
        "default_token": "token-alice",
    }
    values.update(overrides)
    return Settings(**values)


@pytest.fixture(scope="session")
def shop_spec():
    return load_spec(ROOT / "datasets" / "shop_openapi3.json")


@pytest.fixture(scope="session")
def petstore_spec():
    return load_spec(ROOT / "datasets" / "petstore_swagger2.json")


@pytest.fixture(scope="session")
def shop_graph(shop_spec):
    return build_dependency_graph(shop_spec)


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return make_settings(tmp_path)


@pytest.fixture()
def context(tmp_path: Path, shop_spec, shop_graph) -> AgentContext:
    config = ExperimentConfig(condition_id="TEST")
    return AgentContext(
        settings=make_settings(tmp_path),
        spec=shop_spec,
        graph=shop_graph,
        config=config,
        artifact_dir=tmp_path / "artifacts",
        gateway=LLMGateway(DeterministicProvider()),
    )


@pytest.fixture(scope="session")
def live_server():
    with MockAPIServer() as server:
        yield server
