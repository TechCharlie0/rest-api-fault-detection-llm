"""Configuration loading and cost estimation.

Secrets are read from environment variables only.  A local `.env` file is
parsed when present, but values are never printed or written to artifacts.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _float_or_none(name: str) -> float | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _int_or_none(name: str) -> int | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


@dataclass(slots=True)
class Settings:
    root: Path
    artifacts_dir: Path
    datasets_dir: Path
    configs_dir: Path
    llm_provider: str
    llm_api_key: str
    llm_base_url: str
    llm_model: str
    llm_timeout_seconds: float
    llm_max_retries: int
    input_price_per_million: float | None
    output_price_per_million: float | None
    default_base_url: str
    default_token: str
    llm_temperature: float = 0.0
    llm_num_predict: int | None = None
    llm_num_ctx: int | None = None

    @classmethod
    def from_env(cls, root: Path | None = None) -> Settings:
        root = (root or Path(__file__).resolve().parent.parent).resolve()
        _load_dotenv(root / ".env")
        raw_timeout = os.getenv("AGENTICAPI_LLM_TIMEOUT_SECONDS", "60")
        raw_retries = os.getenv("AGENTICAPI_LLM_MAX_RETRIES", "3")
        try:
            timeout = float(raw_timeout)
        except ValueError:
            timeout = 60.0
        try:
            retries = max(0, int(raw_retries))
        except ValueError:
            retries = 3
        return cls(
            root=root,
            artifacts_dir=root / "artifacts",
            datasets_dir=root / "datasets",
            configs_dir=root / "configs",
            llm_provider=os.getenv("AGENTICAPI_LLM_PROVIDER", "openai_compatible"),
            llm_api_key=os.getenv("AGENTICAPI_LLM_API_KEY", "").strip(),
            llm_base_url=os.getenv("AGENTICAPI_LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
            llm_model=os.getenv("AGENTICAPI_LLM_MODEL", "gpt-4o-mini"),
            llm_timeout_seconds=timeout,
            llm_max_retries=retries,
            input_price_per_million=_float_or_none("AGENTICAPI_LLM_PRICE_INPUT_PER_1M"),
            output_price_per_million=_float_or_none("AGENTICAPI_LLM_PRICE_OUTPUT_PER_1M"),
            default_base_url=os.getenv("AGENTICAPI_BASE_URL", "http://127.0.0.1:8765"),
            default_token=os.getenv("AGENTICAPI_TOKEN", "token-alice"),
            llm_temperature=_float_or_none("AGENTICAPI_LLM_TEMPERATURE") or 0.0,
            llm_num_predict=_int_or_none("AGENTICAPI_LLM_NUM_PREDICT"),
            llm_num_ctx=_int_or_none("AGENTICAPI_LLM_NUM_CTX"),
        )

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_api_key)

    def estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float | None:
        if self.input_price_per_million is None or self.output_price_per_million is None:
            return None
        return (
            prompt_tokens / 1_000_000 * self.input_price_per_million
            + completion_tokens / 1_000_000 * self.output_price_per_million
        )
