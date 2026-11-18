# Post-implementation audit

**Date:** November 17, 2026
**Scope:** verify the implemented prototype and its claims, correct unsupported
statements, and label readiness honestly for Dr. Lin Tan.
**Evidence run:** `artifacts/runs/20261117T171353Z-audit-final`

## Bottom line

The harness is implemented and the deterministic results are reproducible. The
audit found one real implementation/documentation mismatch in the legacy oracle and
several overclaims. The legacy baseline was corrected to a faithful `status < 500`
oracle; it now detects **1/12** faults instead of the previously reported 2/12. `C1`
and `C1R` remain at **12/12** with no clean-run false positives.

The LLM conditions are implemented but **BLOCKED**: no real credentials were
available, so no LLM result is claimed. C6 and C7 currently compile to the same
condition, and the C0-vs-C1 comparison is confounded by case count and oracle
strength. This is a credible feasibility prototype, not publication-ready evidence.

## What was verified

| Claim | Audit result | Evidence |
|---|---|---|
| Local OpenAPI/Swagger normalization | **VERIFIED** | tests; two dataset fixtures |
| Mock API with F01–F12 faults | **VERIFIED** | server/store; fault runs |
| Deterministic C1 pipeline | **VERIFIED** | 51 cases, 12/12 detection, 3 seeds |
| C1R randomized variant | **VERIFIED, narrow** | 4/51 functional cases differ per seed |
| Legacy C0 baseline | **CORRECTED / VERIFIED** | faithful `status < 500`; detects only F01 |
| Separate oracle implementation | **PARTIALLY VERIFIED** | separate code, same spec; not independent |
| Multi-agent LLM wiring | **PARTIALLY VERIFIED** | fake-provider C3 run produced 4 role calls |
| Real LLM results C2–C8 | **BLOCKED** | no `AGENTICAPI_LLM_API_KEY`; zero LLM calls |
| C6/C7 as distinct ablations | **NOT IMPLEMENTED** | both have `use_repair=False` |
| Generated pytest artifacts | **VERIFIED, not executed** | compiled/policy-checked; engine executes cases |
| Tests, lint, types, secrets | **VERIFIED** | see commands below |

## Deterministic evidence

All values are means over seeds 1, 2, and 3.

| Condition | Cases | Clean pass | Detected | Rate | Raw evidence |
|---|---:|---:|---:|---:|---|
| `C0_legacy` | 15 | 1.000 | 1/12 | 0.0833 | F01 only |
| `C1_schema` | 51 | 1.000 | 12/12 | 1.0000 | all faults |
| `C1R_randomized` | 51 | 1.000 | 12/12 | 1.0000 | all faults |

C0 uses a faithful legacy oracle: any status below 500 is accepted. It therefore
detects F01 (HTTP 500) but not F12 (200 instead of 201), and it misses F02–F11.
This is the correct behavior for a status-only baseline.

C1/C1R detection is supported by raw `fault_results.json` messages:

| Fault | Detecting case(s) | Message |
|---|---|---|
| F01 | `get_product__functional` | HTTP 500 |
| F02 | `get_product__functional` | `price` is a string |
| F03 | `get_product__functional` | required `name` missing |
| F04 | `create_product__boundary` | expected 400, got 201 |
| F05 | `list_my_orders__auth` | expected 401, got 200 |
| F06 | `get_order__authz` | expected 403, got 200 |
| F07 | `create_product__stateful` | step 4 expected 404, got 200 |
| F08 | `create_order__business_rule` | expected 400, got 201 |
| F09 | `create_order__idempotency` | duplicate order IDs |
| F10 | `get_product__functional` | `stock=-1` |
| F11 | `create_product__negative` | expected 400, got 201 |
| F12 | `create_product__functional`, `create_product__stateful` | expected 201, got 200 |

All clean runs passed (15/15 and 51/51); there were no false positives on the clean
API and no execution errors. Detection counts any non-`PASS` outcome. Several faults
are detected by only one selected case, so 12/12 is genuine but sensitive to case
selection.

## Oracle independence

C0 uses `oracle_mode="legacy"` (`status < 500`). C1 and C1R use the full
status/schema/state/business-rule oracle. C0/C1/C1R share the same mock API and the
same F01–F12 fault set.

The oracle is implemented separately from the generator, but it is derived from the
same OpenAPI document and consumes generated case expectations. It is a **separate
spec-derived implementation**, not an independent oracle. It cannot catch errors in
the specification itself.

The C0-vs-C1 comparison also confounds generation strategy with case count (15 vs
51), technique coverage, and oracle strength. It supports feasibility, not a causal
claim about schema-aware generation.

## C1R scope

C1R randomizes functional request bodies/query values using the seed. It does not
randomize auth, authz, negative, boundary, stateful, idempotency, or business-rule
cases. In every seed, exactly four of 51 cases differ:

- `create_product__functional`
- `update_product__functional`
- `update_user__functional`
- `list_products__functional`

The identical detection outcome is stability evidence for these value changes, not
evidence that randomization is generally beneficial.

## C2–C8 wiring

- `OpenAICompatibleProvider` posts to `{AGENTICAPI_LLM_BASE_URL}/chat/completions`
  and parses `choices[0].message.content`.
- Required environment variables: `AGENTICAPI_LLM_API_KEY`,
  `AGENTICAPI_LLM_BASE_URL`, `AGENTICAPI_LLM_MODEL`.
- Optional: `AGENTICAPI_LLM_TIMEOUT_SECONDS`, `AGENTICAPI_LLM_MAX_RETRIES`,
  `AGENTICAPI_LLM_PRICE_INPUT_PER_1M`, `AGENTICAPI_LLM_PRICE_OUTPUT_PER_1M`.
- `AGENTICAPI_LLM_PROVIDER` is parsed but ignored; only the OpenAI-compatible client
  is implemented.
- C2: default plan plus one LLM generation call; deterministic validation/oracle.
- C3: LLM analysis, planning, generation, and optional repair; deterministic
  validator, executor, and oracle. A fake-provider run produced exactly four calls:
  `spec_analysis`, `planning`, `generation`, `repair`, with matching traces.
- C4: C3 without the Planner (default plan).
- C5: C3 without the validator gate; repair can still re-filter invalid cases.
- C6/C7: both use `use_repair=False`; they are currently the same condition.
- C8: full LLM pipeline with a status-only oracle.
- No credential fallback: `allow_llm_fallback=false` produces `BLOCKED`, never
  deterministic output in an LLM condition.
- `max_cost_usd` and `pytest_timeout_seconds` are configured but not enforced; the
  experiment-level `max_repairs` is not passed through. `AGENTICAPI_TOKEN` is unused.

The fake provider proves wiring and coordination only. It is not evidence of real
model quality, token cost, latency, repair quality, or ablation effects.

## Security and reproducibility

- Only loopback mock APIs are allowed; redirects are disabled.
- `.env` is git-ignored; `.env.example` contains placeholders only.
- Secret scan is clean.
- Generated pytest files are parsed, policy-checked, and compiled, but the
  experiment executes structured cases through `ExecutionEngine`, not the generated
  files.
- Dataset hashes: `sha256sum -c datasets/SHA256SUMS`.
- Artifact hashes: `(cd artifacts/runs/20261117T171353Z-audit-final && sha256sum -c SHA256SUMS)`.
  The manifest covers 488 files.

Verification commands:

```bash
. .venv/bin/activate
pytest -q
pytest --cov=agenticapi --cov-report=term-missing
ruff check agenticapi tests
mypy agenticapi
python scripts/check_secrets.py
sha256sum -c datasets/SHA256SUMS
(cd artifacts/runs/20261117T171353Z-audit-final && sha256sum -c SHA256SUMS)
```

Observed results after the audit fix: 51 tests passed, 80% aggregate coverage, ruff
clean, mypy clean across 42 source files, secret scan clean, dataset and artifact
hashes valid.

## Corrections applied

- Fixed C0's legacy oracle to use `status < 500`; added a regression assertion that
  it detects only F01 and misses F12.
- Reran all deterministic conditions into the audit-final evidence run.
- Corrected README, architecture, research design, evaluation, technical report,
  limitations, readiness, LLM setup, and artifact documentation.
- Corrected the fault catalogue table to match `agenticapi/evaluation/faults.py` and
  the mock server.
- Added artifact integrity manifest `SHA256SUMS`.

## Remaining work before real LLM experiments

1. Make C6 distinct from C7, or remove the duplicate from the ablation suite.
2. Make C5's semantics explicit: no validator gate, but repair may still reject
   invalid cases.
3. Either pass `max_cost_usd`/`max_repairs`/`pytest_timeout_seconds` through or stop
   documenting them as active controls.
4. Add a second structurally different API and an independent/human-authored oracle.
5. Run a small real LLM pilot with repeated seeds and report distributions, cost,
   latency, and failures.

## Final labels

- **Deterministic harness:** IMPLEMENTED / VERIFIED.
- **C0 baseline:** IMPLEMENTED / VERIFIED after correction.
- **C1/C1R results:** VERIFIED on one synthetic fixture.
- **Oracle independence:** PARTIALLY IMPLEMENTED / spec-coupled.
- **C2–C8 wiring:** PARTIALLY IMPLEMENTED / real runs BLOCKED.
- **C6/C7 ablation:** NOT IMPLEMENTED as distinct conditions.
- **Real LLM evidence:** BLOCKED.
- **Publication-level novelty:** NOT IMPLEMENTED / out of scope.
