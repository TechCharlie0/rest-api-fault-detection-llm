# Experimental Setup

This document describes the software, model, datasets, configuration, dependencies,
and experiment setup for the AgenticAPI research project.

## Provenance

Reported outcomes are from the authoritative current implementation: the five-seed
Phase 4 execution (`artifacts/runs/20261118T090640Z-phase4-final`) plus the verified
three-seed default-configuration runs for `C1R_randomized`. The historical audit
snapshot (`artifacts/runs/20261117T171353Z-audit-final`, prior implementation
revision) reported 12/12 for `C1_schema`/`C1R_randomized`; those values are superseded
by the current implementation's 10/12 and are retained only as preserved history.

## Dataset

| Property | Value |
|---|---|
| **Primary dataset** | `shop_openapi3.json` (OpenAPI 3.0) |
| **Secondary dataset** | `petstore_swagger2.json` (Swagger 2.0) |
| **SHA-256 (primary)** | `4a1d500a6203521748be0972bd78505bcd4483fb252c475f0c583e386941f74b` |
| **SHA-256 (secondary)** | `bb116730d391e330119c691f9b124d07b9afdea61b5a252345b577e9a4c2f98b` |
| **SHA-256 verification** | `sha256sum -c datasets/SHA256SUMS` → both fixtures OK |
| **Operations** | 15 (product, order, user, health, inventory domains) |
| **Fault catalogue** | 12 independently injectable faults in local mock API |

### Dataset verification

The fixture hashes were verified with:

```
sha256sum -c datasets/SHA256SUMS
```

Both `datasets/shop_openapi3.json` and `datasets/petstore_swagger2.json` matched their
expected values.

## Model and Provider

| Property | Value |
|---|---|
| **LLM model** | `qwen2.5:1.5b` via Ollama (Phase 4 pilot only) |
| **Ollama endpoint** | `http://localhost:11434` |
| **Seed handling** | Outer run seed is passed to the LLM provider as the model seed; seeds are not independent replicates |
| **Mock API** | Local loopback server, port 8765 |
| **Execution safety** | Executor rejects non-loopback hosts |

### Ollama setup

1. Install Ollama from https://ollama.ai
2. Start the Ollama server: `ollama serve`
3. Pull the model: `ollama pull qwen2.5:1.5b`
4. Verify: `ollama run qwen2.5:1.5b "hello"`

In the default configuration without credentials, conditions C2–C8 are marked
`BLOCKED` and no real LLM calls are made. Deterministic conditions
(C0_legacy, C1_schema, C1R_randomized) work without any LLM credentials. Phase 4
executed C2_single_llm and C3_multi_llm with local Ollama; C4–C8 remain unevaluated.

## Experimental Conditions

See `methodology.md` for the complete condition table. Summary:

| Condition | Seeds | LLM required | Status |
|---|---|---|---|
| **C0_legacy** | 1–5 | no | Executed; deterministic (Phase 4) |
| **C1_schema** | 1–5 | no | Executed; deterministic (Phase 4) |
| **C1R_randomized** | 1–3 | no | Executed; deterministic (verified default configuration) |
| **C2_single_llm** | 1–5 | yes | Executed in Phase 4 with local Ollama; blocked in default no-key configuration |
| **C3_multi_llm** | 1–5 | yes | Executed in Phase 4 with local Ollama; blocked in default no-key configuration |
| **C4_no_planner** | — | yes | Not evaluated; blocked in default no-key configuration |
| **C5_no_validator** | — | yes | Not evaluated; blocked in default no-key configuration |
| **C6_no_execution_feedback** | — | yes | Not evaluated; blocked in default no-key configuration |
| **C7_no_repair** | — | yes | Not evaluated; blocked in default no-key configuration |
| **C8_status_oracle** | — | yes | Not evaluated; blocked in default no-key configuration |

## Configuration

Experiment configuration is defined in:

- `configs/default.json` – lists all ten conditions with seeds 1–3; without LLM
  credentials, C2–C8 are blocked and only the deterministic conditions execute.
- `configs/smoke.json` – smoke configuration, runs C0_legacy, C1_schema, and
  C1R_randomized with seed 1.

Configuration keys include:

- `name` – run label
- `spec_path` – local OpenAPI/Swagger document
- `conditions` – list of condition IDs to run
- `seeds` – list of seed numbers per condition
- `output_dir` – artifact root
- `max_cases_per_operation` – generation cap per operation
- `max_repairs` – maximum repair attempts
- `max_llm_calls` – per-run LLM call cap
- `max_cost_usd` – per-run cost cap
- `allow_llm_fallback` – whether fallback output is permitted
- `notes` – human-readable run note

LLM provider settings are read from environment variables, not from the JSON
configuration files.

## Dependencies

### Runtime dependencies (from pyproject.toml)

```
requests==2.32.5
jsonschema==4.26.0
```

### Development dependencies (from pyproject.toml dev)

```
pytest==9.2.0
pytest-cov==7.0.0
ruff==0.14.6
mypy==1.19.0
types-requests==2.32.4.20250913
```

A fully pinned local environment is recorded in `requirements-txt.txt`.

### Optional

- Ollama and `qwen2.5:1.5b` model for the Phase 4 LLM pilot
- `make` for Makefile commands

## Configuration Files

### configs/default.json

```json
{
  "name": "agenticapi-default",
  "spec_path": "datasets/shop_openapi3.json",
  "conditions": [
    "C0_legacy",
    "C1_schema",
    "C1R_randomized",
    "C2_single_llm",
    "C3_multi_llm",
    "C4_no_planner",
    "C5_no_validator",
    "C6_no_execution_feedback",
    "C7_no_repair",
    "C8_status_oracle"
  ],
  "seeds": [1, 2, 3],
  "output_dir": "artifacts/runs",
  "max_cases_per_operation": 8,
  "max_repairs": 2,
  "max_llm_calls": 60,
  "max_cost_usd": 1.0,
  "allow_llm_fallback": false,
  "notes": "Deterministic conditions run without credentials; LLM conditions are blocked if no key is configured."
}
```

### configs/smoke.json

```json
{
  "name": "agenticapi-smoke",
  "spec_path": "datasets/shop_openapi3.json",
  "conditions": ["C0_legacy", "C1_schema", "C1R_randomized"],
  "seeds": [1],
  "output_dir": "artifacts/runs",
  "max_cases_per_operation": 8,
  "max_llm_calls": 60,
  "allow_llm_fallback": false
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
