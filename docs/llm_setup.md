# Enabling real LLM conditions

## Current status

No real LLM API key is configured in this environment. `C2`–`C8` are therefore
reported as `BLOCKED`. The deterministic conditions `C0`, `C1`, and `C1R` do not
need a key and have been executed.

## Configuration

Set environment variables in `.env` (git-ignored) or the shell:

```bash
export AGENTICAPI_LLM_API_KEY=...
export AGENTICAPI_LLM_MODEL=gpt-4o-mini
export AGENTICAPI_LLM_BASE_URL=https://api.openai.com/v1
export AGENTICAPI_LLM_PRICE_INPUT_PER_1M=0.15
export AGENTICAPI_LLM_PRICE_OUTPUT_PER_1M=0.60
```

Use an OpenAI-compatible endpoint if needed. `AGENTICAPI_LLM_PROVIDER` is parsed for
backward compatibility but does **not** select a client; only the OpenAI-compatible
chat-completions client is implemented. Set the prices to the provider's current
values; leaving them unset disables cost estimates but still records token counts
when the provider reports usage. `max_cost_usd` is configured but not enforced, so
monitor provider-side usage during a pilot.

The provider is never silently downgraded. If the key is absent, LLM conditions are
blocked. If a call fails and fallback is disabled, the condition fails with an
explicit error instead of mixing deterministic output into an LLM result.

`allow_llm_fallback=false` is the default. Real-provider calls are implemented in
`OpenAICompatibleProvider`; `DeterministicProvider` and `FakeLLMProvider` are never
substituted for a real model in an experiment.

## Run

```bash
. .venv/bin/activate
python -m agenticapi run --config configs/default.json \
  --conditions C2_single_llm,C3_multi_llm,C4_no_planner,C5_no_validator,C6_no_execution_feedback,C7_no_repair,C8_status_oracle \
  --seeds 1 --label llm-pilot
```

This runs one seed of the seven LLM/ablation conditions. The default config is not
modified. Do not present C6 as an execution-feedback ablation until it is made
distinct from C7. C5 removes the validator gate, but repair can still reject invalid
cases; document that interpretation before reporting results.

## Data handling

Prompts contain bounded spec excerpts and generated request data. With the current
fixtures this is synthetic mock data, not personal or production data. Do not point
the pipeline at a private API without a data-handling review.

Do not paste keys into prompts, logs, or chat. The gateway redacts obvious secrets,
but redaction is not a guarantee.

## Expected artifacts

LLM conditions write the same artifacts as deterministic conditions, plus token and
cost fields in `condition_result.json`. Until those runs exist, do not report LLM
metrics.
