# AgenticAPI: A Local Feasibility Study of Schema-Aware, Fault-Injected REST API Test Generation

**Status:** research prototype; deterministic evaluation complete, LLM evaluation blocked
**Date:** November 17, 2026
**Environment:** Python 3.14.3, local loopback mock API, no real LLM credentials

## Abstract

AgenticAPI is a local testbed for comparing REST API test-generation strategies
under controlled fault injection. It normalizes OpenAPI/Swagger documents, plans test
techniques, generates executable cases, validates them, executes them against a
seeded mock API, and judges outcomes with a specification-derived oracle. The study
compares a legacy-style baseline (`C0`) with a deterministic schema-aware pipeline
(`C1`), a randomized-value variant (`C1R`), and seven LLM/ablation conditions
(`C2`–`C8`). On one synthetic 15-operation shop API with twelve injected faults,
`C0` detected 1/12 faults (8.3%), while `C1` and `C1R` detected 12/12 (100%) with a
clean pass rate of 1.0. The LLM conditions are blocked because no API key was
available. These results establish that the local harness works and that the
schema-aware strategy is worth evaluating further; they do not establish
generalization, LLM benefit, or publication readiness.

## 1. Motivation

REST API test generation is often evaluated with either hand-written tests or
uncontrolled real services. That makes it difficult to isolate which capability - schema
understanding, planning, validation, execution feedback, or repair - is responsible
for an outcome. AgenticAPI addresses this by combining a local mock service, an
explicit fault catalogue, and condition-level ablations. The target research question
is whether schema-aware, agentic test generation improves fault detection over a
legacy template baseline without sacrificing clean-pass reliability.

## 2. System

The pipeline has seven stages:

1. **Normalize** an OpenAPI 3.x or Swagger 2.0 document into a common `APISpec`.
2. **Analyze** operations with a deterministic risk model, optionally enriched by an
   LLM note.
3. **Plan** techniques from schema, auth, state, and declared business rules.
4. **Generate** functional, negative, boundary, auth, authorization, stateful,
   idempotency, and business-rule cases.
5. **Validate** each case against documented paths, methods, parameters, captures,
   and expected statuses.
6. **Render** standalone pytest artifacts and policy-check their source.
7. **Execute and judge** against a loopback mock API, clean and then fault-injected.

The mock shop API has products, orders, users, admin endpoints, bearer tokens,
multipart upload, and seeded state. The admin API resets state and injects one of
twelve faults, including wrong statuses, missing fields, ignored auth, removed role
checks, stock-rule violations, soft-delete leaks, invalid input acceptance, and
idempotency duplication.

The oracle checks declared status codes, response schemas, state transitions, and
business rules. It does not fall back to accepting any 2xx response when a status is
declared. The legacy baseline instead uses a faithful `status < 500` oracle, which
accepts a 200 where 201 is required. The oracle is implemented separately from the
generator but shares the same OpenAPI specification, so it is a separate
implementation rather than an independent oracle.

The LLM layer implements an OpenAI-compatible chat-completions client. It validates
structured JSON, retries malformed output, counts tokens, optionally estimates cost,
and redacts secrets. Deterministic output and LLM output are labeled separately.
Without a key, LLM conditions are marked `BLOCKED`, never silently replaced.

## 3. Method

### Conditions

`C0_legacy` generates one functional template per operation and uses a faithful
`status < 500` oracle. `C1_schema` uses deterministic planning, technique-specific
generation, validation, and a schema/state/business-rule oracle. `C1R_randomized`
changes functional request bodies/query values with a seed; technique-specific cases
are unchanged.

`C2` uses one LLM generation call with the default plan. `C3` adds LLM analysis,
planning, generation, and repair while keeping validation, execution, and judging
deterministic. `C4` removes the Planner, `C5` removes the validator gate, `C6`/`C7`
run without repair, and `C8` uses a status-only oracle with the LLM pipeline. `C6` and
`C7` currently compile to the same configuration, so C6 is not a distinct
execution-feedback ablation.

### Procedure

Each condition was run for seeds 1, 2, and 3. Cases were executed against a clean
mock first. The state was then reset and each fault was injected independently. A
fault counts as detected if at least one case fails under that fault. Artifacts are
written per condition/seed, and aggregate metrics are written to `summary.json`,
`results.csv`, and SVG charts.

### Measures

- clean pass rate (higher is better);
- fault detection rate over twelve faults (higher is better);
- missed fault IDs;
- case count, validity, duration, LLM calls, tokens, and estimated cost.

## 4. Results

| Condition | Cases | Clean pass | Detected | Detection rate | Status |
|---|---:|---:|---:|---:|---|
| `C0_legacy` | 15 | 1.000 | 1/12 | 0.083 | COMPLETED |
| `C1_schema` | 51 | 1.000 | 12/12 | 1.000 | COMPLETED |
| `C1R_randomized` | 51 | 1.000 | 12/12 | 1.000 | COMPLETED |
| `C2`–`C8` | 0 | n/a | n/a | n/a | BLOCKED |

`C0` detected only a product-read HTTP 500 (`F01`). It missed `F12` because its
status `< 500` oracle accepts a 200 response even though 201 is required; it also
missed schema changes, ignored authentication, removed authorization, stock-rule
violations, soft-delete leaks, invalid input, and idempotency duplication. `C1`
detected all twelve with no clean-run false positives. The 51 `C1` cases comprised
15 functional, 11 auth, 8 authorization, 7 negative, 4 boundary, 3 business-rule, 2
stateful, and 1 idempotency case.

Quality evidence: 51 tests passed, coverage was 80% aggregate, `ruff` was clean, and
`mypy` was clean across 42 source files. Generated test artifacts compiled and passed
the source policy check.

## 5. Discussion

The deterministic result is consistent with the design hypothesis: the full pipeline
finds faults that the legacy baseline cannot. The comparison is confounded, however:
`C0` uses 15 cases and a status `< 500` oracle, while `C1` uses 51 cases and a full
status/schema/rule oracle. The result therefore does not isolate the contribution of
schema-aware generation, technique coverage, or oracle strength.

`C1R` changed exactly 4 of 51 functional cases and produced the same outcome on this
fixture. That is stability evidence for these value changes, not evidence that
randomization is generally beneficial.

The result should not be read as an LLM result. `C1` is deterministic. The LLM
integration is implemented and unit-tested with a fake provider, but real model
behavior, token cost, latency, repair quality, and agent coordination effects are
unmeasured. The ablation conditions cannot yet answer whether planning, validation,
repair, or execution feedback matters.

The clean pass rate of 1.0 is also a caution: this is a small, controlled fixture
whose behavior and faults were authored together. A realistic API would introduce
noise, undocumented behavior, and specification errors that this study does not
model.

## 6. Threats to validity

Internal validity is threatened by coupling between the mock, faults, and oracle, by
the baseline being a reimplementation rather than a historical run, and by the
C0/C1 case-count and oracle-strength confound. External
validity is limited by one synthetic API. Construct validity is limited by binary
fault detection and machine-only case judgment. Conclusion validity is limited by
three deterministic seeds and no inferential statistics. LLM conclusions are
blocked entirely.

## 7. Conclusion and next steps

AgenticAPI now provides a working, local, reproducible harness for controlled REST
API test-generation experiments. The deterministic evidence supports a larger study;
it does not support claims of novelty, generalization, or LLM superiority. The next
steps are to configure a real provider, run `C2`–`C8`, add at least two structurally
different specs and a second independent oracle, and report confidence intervals
over repeated stochastic runs.

## Reproducibility

```bash
. .venv/bin/activate
pytest -q
ruff check agenticapi tests
mypy agenticapi
python -m agenticapi run --config configs/default.json --label audit-final
```

Verify fixture and artifact hashes:

```bash
sha256sum -c datasets/SHA256SUMS
(cd artifacts/runs/20261117T171353Z-audit-final && sha256sum -c SHA256SUMS)
```

See `docs/evaluation.md` for artifact paths and `docs/limitations.md` for the full
threat list.
