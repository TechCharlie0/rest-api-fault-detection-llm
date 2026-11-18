# Reproducibility

This document provides complete instructions for another researcher to reproduce
the experiments from the AgenticAPI project.

## Prerequisites

### Supported Python version

Python >= 3.12 (the project requires-python = ">=3.12").

### Virtual environment creation

```bash
python3 -m venv .venv
# Activate the virtual environment
# On macOS/Linux:
. .venv/bin/activate
# On Windows:
.\venv\Scripts\activate.bat
```

### Ollama installation (required for LLM conditions)

1. Install Ollama from https://ollama.ai
2. Start the Ollama server:
   ```bash
   ollama serve
   ```
3. Pull the model:
   ```bash
   ollama pull qwen2.5:1.5b
   ```
4. Verify the model is available:
   ```bash
   ollama run qwen2.5:1.5b "hello"
   ```

### System dependencies

- `requests` Python package (for HTTP execution against mock API)
- `jsonschema` Python package (for OpenAPI validation)
- `make` (for Makefile commands, optional)

## Environment Configuration

### Copy the environment template

```bash
cp .env.example .env
```

### Edit `.env` as needed

The `.env.example` file provides the template:

```
# AgenticAPI environment template. Copy to .env only if you need local LLM calls.
# Never commit .env or real credentials.

# Deterministic baseline and local mock API work without any of these.
# Parsed for compatibility; currently does not select a client.
AGENTICAPI_LLM_PROVIDER=openai_compatible
AGENTICAPI_LLM_API_KEY=
AGENTICAPI_LLM_BASE_URL=https://api.openai.com/v1
AGENTICAPI_LLM_MODEL=gpt-4o-mini
AGENTICAPI_LLM_TIMEOUT_SECONDS=60
AGENTICAPI_LLM_MAX_RETRIES=3

# Optional price table for cost estimation. Leave unset if unknown; costs are
# reported as unknown rather than fabricated.
AGENTICAPI_LLM_PRICE_INPUT_PER_1M=
AGENTICAPI_LLM_PRICE_OUTPUT_PER_1M=

# Local execution only. The runner refuses non-loopback hosts.
AGENTICAPI_BASE_URL=http://127.0.0.1:8765
# Present for local mock compatibility; the executor uses fixed mock tokens.
AGENTICAPI_TOKEN=token-alice
```

For deterministic baseline experiments (C0_legacy, C1_schema, C1R_randomized),
no LLM API key is needed. The deterministic conditions work with the local mock
API only.

## Verifying the Dataset

### SHA-256 verification

```bash
# Compute the SHA-256 hash
sha256sum datasets/shop_openapi3.json

# Expected value:
# 4a1d500a6203521748be0972bd78505bcd4483fb252c475f0c583e386941f74b
```

The computed hash must match the expected value `4a1d500a6203521748be0972bd78505bcd4483fb252c475f0c583e386941f74b`.
If it does not match, do not proceed until the dataset is verified.

## Running the Check Command

```bash
python -m agenticapi check
```

This command validates:

- Python version (>= 3.12)
- Installed dependencies (from requirements-txt.txt)
- Ollama server availability at `http://localhost:11434`
- `qwen2.5:1.5b` model availability
- Configuration status (LLM conditions reported as BLOCKED when no key is present)

### Expected output (without LLM key)

```
$ python -m agenticapi check
Python 3.12.x OK
Dependencies OK
Ollama: http://localhost:11434
Model: qwen2.5:1.5b Available
LLM API key: not configured (LLM conditions BLOCKED)
Configuration: smoke
```

### Expected output (with LLM key configured)

When `AGENTICAPI_LLM_API_KEY` is set in `.env`, the output will include:

```
LLM API key: configured (LLM conditions ACTIVE)
```

## Running Experiments

### Smoke configuration (minimal)

```bash
python -m agenticapi run --config configs/smoke.json
```

This runs the two executable conditions (C0_legacy, C1_schema) with seed 1 only.
LLM conditions (C2–C8) are automatically skipped with a BLOCKED label.

### Default configuration (all executable conditions)

```bash
python -m agenticapi run --config configs/default.json
```

This runs all three executable conditions (C0_legacy, C1_schema, C1R_randomized)
with seeds 1–3. LLM conditions are automatically skipped.

### Full configuration (all conditions, including blocked)

If LLM credentials are configured, the runner will attempt all conditions.
If no LLM key is present, conditions C2–C8 are marked BLOCKED and skipped.

### Individual condition execution

```bash
python -m agenticapi run-condition C1_schema --seed 1
```

Runs a single condition with a specific seed.

## Artifact Locations

Per-run artifacts are written to `artifacts/runs/<timestamp>/`, where `<timestamp>`
is the generation timestamp in `YYYYMMDDTHHMMSSZ` format.

### Directory structure per condition/seed

```
artifacts/runs/<timestamp>/C0_legacy/seed-1/
├── condition_result.json     ← metrics, fault-level matrix, ground truth
├── generated_tests/          ← pytest test files
├── orchestrator.log          ← execution log
└── ...                       ← other run artifacts

artifacts/runs/<timestamp>/C1_schema/seed-1/
├── condition_result.json
├── generated_tests/
└── orchestrator.log

artifacts/runs/<timestamp>/C1R_randomized/seed-1/
├── condition_result.json
├── generated_tests/
└── orchestrator.log
```

### Key artifact files

- `condition_result.json` – Contains the full fault-level matrix (tp/fp/fn/tn),
  precision, recall, F1-score, accuracy, opportunity_faults, and ground truth
  information per condition and seed.
- `orchestrator.log` – Execution log showing condition, seed, cases generated,
  cases passed, cases failed, and any BLOCKED status.
- `generated_tests/` – Directory containing one pytest file per generated test
  case. Each file is self-contained and uses only `requests`, `json`,
  `base64`, and `agenticapi`.

## Reproducing the Results Table

To reproduce the results table in the README and `docs/results.md`:

1. Run the smoke configuration as described above.
2. Ensure Ollama is running with `qwen2.5:1.5b`.
3. Verify the dataset SHA-256 matches the expected value.
4. Check the `artifacts/runs/` directory for per-run `condition_result.json` files.
5. Import the metrics from each `condition_result.json` using `agenticapi.evaluation.metrics.summarize()`.
6. Aggregate the per-condition metrics across seeds (all seeds are identical,
   so take the first seed's results per condition).
7. Construct the results table as shown in `docs/results.md`.

## What is NOT required for reproducibility

- LLM API credentials for the deterministic baseline experiments (C0_legacy,
  C1_schema, C1R_randomized). These work without any LLM key.
- Multiple OpenAPI specifications. The experiment uses one spec only.
- Statistical evaluation across multiple runs. The deterministic conditions
  produce identical results per seed; no inferential statistics are warranted.

## Verification Steps

After running experiments, verify:

1. All 20 condition-seed result files are present and valid (or the 15 files for
   the smoke configuration with 3 seeds).
2. Dataset SHA-256 matches the expected value.
3. `ruff check agenticapi tests` passes (linting).
4. `mypy agenticapi` passes (type checking, with `ignore_missing_imports`).
5. `pytest -q` passes (test suite).
6. The `condition_result.json` files contain the expected fields:
   `tp`, `fp`, `fn`, `tn`, `precision`, `recall`, `f1`, `accuracy`,
   `opportunity_faults`, `ground_truth`.

## Citation for Reproduced Results

If you reproduce the experiments and wish to cite the results, use the following
citation (same as the project citation):

```
Kandel, I. (2026). Beyond Schema-Based Testing: An Empirical Evaluation of
Feedback-Driven Multi-Agent LLM Systems for REST API Fault Detection [Unpublished
research implementation]. GitHub repository: https://github.com/TechCharlie0/rest-api-fault-detection-llm
```

This is an unpublished research implementation; no publication, acceptance,
funding, or institutional affiliation is claimed or implied.