# Experimental Setup

This document describes the software, model, datasets, configuration, dependencies,
and experiment setup for the AgenticAPI research project.

## Dataset

| Property | Value |
|---|---|
| **Primary dataset** | `shop_openapi3.json` (OpenAPI 3.0) |
| **Secondary dataset** | `petstore.json` (Swagger 2.0) |
| **SHA-256 (primary)** | `4a1d500a6203521748be0972bd78505bcd4483fb252c475f0c583e386941f74b` |
| **SHA-256 verification** | Computed SHA-256 matches expected value: **PASS** |
| **Operations** | 15 (product, order, user, health, inventory domains) |
| **Fault catalogue** | 12 independently injectable faults in local mock API |

### Dataset verification

The SHA-256 hash of `datasets/shop_openapi3.json` was computed and compared against
the expected value recorded in the run metadata. The comparison result is:

```
Dataset SHA-256 PASS: 4a1d500a6203521748be0972bd78505bcd4483fb252c475f0c583e386941f74b
(file: /home/isha/Desktop/ai_re-main/datasets/shop_openapi3.json)
```

## Model and Provider

| Property | Value |
|---|---|
| **LLM model** | `qwen2.5:1.5b` via Ollama |
| **Ollama endpoint** | `http://localhost:11434` |
| **Deterministic model seed** | 5 (used for C3 multi-agent conditions) |
| **Mock API** | Local loopback server, port 8765 |
| **Execution safety** | Executor rejects non-loopback hosts |

### Oll setup

1. Install Ollama from https://ollama.ai
2. Start the Ollama server: `ollama serve`
3. Pull the model: `ollama pull qwen2.5:1.5b`
4. Verify: `ollama run qwen2.5:1.5b "hello"`

When the LLM API key is not configured, all conditions C2–C8 are automatically
marked `BLOCKED` and no real LLM calls are made. Deterministic conditions
(C0_legacy, C1_schema, C1R_randomized) work without any LLM credentials.

## Experimental Conditions

See `methodology.md` for the complete condition table. Summary:

| Condition | Seeds | LLM required | Status |
|---|---|---|---|
| **C0_legacy** | 1–5 | no | Executed; deterministic |
| **C1_schema** | 1–5 | no | Executed; deterministic |
| **C1R_randomized** | 1–5 | no | Executed; deterministic |
| **C2_single_llm** | 1–5 | yes | Blocked: no LLM key |
| **C3_multi_llm** | 1–5 | yes | Blocked: no LLM key |
| **C4_no_planner** | 1–5 | yes | Blocked: no LLM key |
| **C5_no_validator** | 1–5 | yes | Blocked: no LLM key |
| **C6_no_execution_feedback** | 1–5 | yes | Blocked: no LLM key |
| **C7_no_repair** | 1–5 | yes | Blocked: no LLM key |
| **C8_status_oracle** | 1–5 | yes | Blocked: no LLM key |

## Configuration

Experiment configuration is defined in:

- `configs/default.json` – default experiment configuration, runs all executable
  conditions with seeds 1–3.
- `configs/smoke.json` – smoke configuration, runs the three executable conditions
  with a minimal setup.

Configuration keys include:
- `conditions` – list of condition IDs to run
- `seeds` – list of seed numbers per condition
- `LLM_API_KEY` – optional; when absent, LLM conditions are blocked
- `mock_api_port` – port for the local mock API
- `orchestrator` – experiment runner settings

## Dependencies

### Core dependencies (from requirements-txt.txt)

```
attrs==26.1.0
certifi==2026.10.23
charset-normalizer==3.5.2
idna==3.20
iniconfig==2.3.1
jsonschema==4.26.0
jsonschema-specifications==2025.9.1
pathspec==1.1.1
pluggy==1.7.0
Pygments==2.21.0
requests==2.32.5
rpds-py==2026.9.1
urllib3==2.8.0
```

### Development dependencies (from pyproject.toml dev)

```
pytest==9.2.0
pytest-cov==7.0.0
ruff==0.14.6
mypy==1.19.0
types-requests==2.32.4.20250913
typing-extensions==4.16.0
```

### Optional

- Ollama and `qwen2.5:1.5b` model for LLM conditions
- `make` for Makefile commands

## Configuration Files

### configs/default.json

```json
{
  "conditions": ["C0_legacy", "C1_schema", "C1R_randomized"],
  "seeds": [1, 2, 3],
  "mock_api_port": 8765,
  "LLM_API_KEY": "",
  "orchestrator": {
    "write_artifacts": true,
    "generate_charts": true
  }
}
```

### configs/smoke.json

```json
{
  "conditions": ["C0_legacy", "C1_schema"],
  "seeds": [1],
  "mock_api_port": 8765,
  "LLM_API_KEY": "",
  "orchestrator": {
    "write_artifacts": true,
    "generate_charts": false
  }
}
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `AGENTICAPI_LLM_API_KEY` | (empty) | LLM API key for OpenAI-compatible provider |
| `AGENTICAPI_LLM_BASE_URL` | `https://api.openai.com/v1` | Base URL for LLM provider |
| `AGENTICAPI_LLM_MODEL` | `gpt-4o-mini` | LLM model name |
| `AGENTICAPI_LLM_PROVIDER` | `openai_compatible` | Provider identifier (parsed but does not select client) |
| `AGENTICAPI_BASE_URL` | `http://127.0.0.1:8765` | Local mock API base URL |
| `AGENTICAPI_TOKEN` | `token-alice` | Mock API authentication token |

The `.env.example` file provides the template. The `.env` file is git-ignored; real
credentials must never be committed.