# Results

This document presents the experimental results from the AgenticAPI research
project, with honest interpretation and clear identification of confounded
findings and unevaluated conditions.

## Provenance

Results below are reported from two sources, kept distinct:

- **Authoritative current implementation.** The committed code reproduces the
  five-seed **Phase 4** execution (`artifacts/runs/20261118T090640Z-phase4-final`,
  seeds 1–5, local Ollama `qwen2.5:1.5b`). A fresh `configs/smoke.json` run at the
  current revision reproduces the deterministic Phase 4 values exactly.
- **Historical audit snapshot.** `artifacts/runs/20261117T171353Z-audit-final`
  (three seeds) was produced by a prior implementation revision and reports
  12/12 for `C1_schema` and `C1R_randomized`. Those values are superseded by the
  current implementation, which reports 10/12, and are retained only as preserved
  history.

`C1R_randomized` was not part of Phase 4. Its verified values come from the
default-configuration runs at the current revision (three seeds), where it matches
`C1_schema`; the historical audit snapshot reported 12/12 for both.

## Executive Summary

- **C1_schema** (schema-based deterministic) detected 10 of 12 injected faults
  (detection rate 0.8333), with 51 generated cases and a 1.00 clean pass rate.
  Among the 10 faults for which the suite had an opportunity, detection was
  10/10 (opportunity-adjusted rate 1.00); F04 and F11 had no opportunity.
- **C0_legacy** (conventional) detected 1/12 faults (0.0833 rate), with 15
  generated cases and a 1.00 clean pass rate.
- **C1R_randomized** matched C1_schema (10/12, F1 = 1.0) in the verified
  default-configuration runs; Phase 4 did not include C1R.
- **C2_single_llm** and **C3_multi_llm** were executed in Phase 4 with a local
  Ollama model: C2 detected 5/12 faults on average (F1 = 0.8333) and C3 detected
  4/12 (F1 = 0.4706). C4–C8 were not evaluated.
- The C1-vs-C0 comparison is confounded by case count (51 vs 15) and oracle
  strength (full status/schema/state/rules vs `status < 500`). The experiment
  does not isolate the effect of schema-aware generation from the effect of a
  stronger oracle or larger case count.

## Detailed Results Table

Phase 4 rows (`C0_legacy`, `C1_schema`, `C2_single_llm`, `C3_multi_llm`) are
five-seed means; the `C1R_randomized` row is from the verified three-seed default
configuration.

| Condition | Seeds | Cases per run | Clean pass rate | Faults detected | Detection rate | Precision | Recall | F1-score | Opportunity-adjusted detection |
|---|---|---|---|---|---|---|---|---|---|
| **C0_legacy** | 1–5 | 15 | 1.00 | 1 / 12 | 0.0833 | 1.000 | 0.200 | 0.333 | 0.2000 |
| **C1_schema** | 1–5 | 51 | 1.00 | 10 / 12 | 0.8333 | 1.000 | 1.000 | 1.000 | 1.0000 |
| **C1R_randomized** | 1–3 | 51 | 1.00 | 10 / 12 | 0.8333 | 1.000 | 1.000 | 1.000 | 1.0000 |
| **C2_single_llm** | 1–5 | 12 | 0.7500 | 5 / 12 | 0.4167 | 0.8333 | 0.8333 | 0.8333 | 0.8333 |
| **C3_multi_llm** | 1–5 | 11 | 0.4545 | 4 / 12 | 0.3333 | 0.4000 | 0.5714 | 0.4706 | 0.5714 |
| **C4_no_planner** | — | — | — | — | — | — | — | — | — |
| **C5_no_validator** | — | — | — | — | — | — | — | — | — |
| **C6_no_execution_feedback** | — | — | — | — | — | — | — | — | — |
| **C7_no_repair** | — | — | — | — | — | — | — | — | — |
| **C8_status_oracle** | — | — | — | — | — | — | — | — | — |

## Per-Condition Details

### C0_legacy

- One functional template per operation; `status < 500` oracle.
- Detected fault F01 (HTTP 500 on `GET /products/p1`).
- Missed fault F12 (HTTP 200 instead of 201 on `POST /products`) because the
  faithful legacy oracle accepts any status below 500, so a 200 instead of 201 is
  not classified as a failure.
- 15 generated cases across 15 operations; all cases pass on the clean mock API.

### C1_schema

- Deterministic schema-aware planning, generation, validation, with spec oracle.
- Detected 10 of the 12 injected faults, spanning schema, auth, authz, state,
  business-rule, boundary, and idempotency categories.
- F04 and F11 had no opportunity: F04 is a boundary fault that requires specific
  test case construction, and F11 is a schema/validation fault requiring a missing
  name input. Their non-detection does not indicate a generation weakness.
- 51 generated cases across 15 operations; all cases pass on the clean mock API.

### C1R_randomized

- `C1` with seeded randomized functional bodies/query values; technique-specific
  cases unchanged.
- Matches C1_schema exactly (10/12, F1 = 1.0) in the verified default-configuration
  runs. The deterministic technique-specific cases, not the randomized functional
  values, drive detection.
- 51 generated cases per run; 1.00 clean pass rate.

### C2_single_llm and C3_multi_llm (Phase 4)

- Executed with a local Ollama `qwen2.5:1.5b` model, deterministic validation and
  oracle, five seeds each. Per-seed outcomes were identical within each condition.
- C2: 12 cases, 5/12 faults, precision = recall = F1 = 0.8333, clean pass rate
  0.7500.
- C3: 11 cases, 4/12 faults, precision 0.4000, recall 0.5714, F1 0.4706, clean
  pass rate 0.4545.
- C4–C8 were not evaluated; no results are claimed for them.

## Key Observations

1. **Schema-aware generation is effective**: C1_schema detected 10/12 faults
   (F04 and F11 had no opportunity), while C0_legacy detects only 1.

2. **Case count and oracle strength confounded**: C1 uses 51 cases and a much
   stronger oracle than C0 (15 cases, `status < 500`). Both likely contribute.

3. **Randomized functional values do not degrade reliability**: C1R_randomized
   achieves the same detection as C1_schema.

4. **Single-agent LLM outperformed the multi-agent pipeline in Phase 4**: C2
   (F1 = 0.8333) exceeded C3 (F1 = 0.4706), and C3 showed a lower clean pass rate
   (0.4545) consistent with more false positives.

5. **Honest observation on multi-agent potential**: Increasing the number of agents
   and adding feedback loops does not automatically improve fault detection; the
   multi-agent pipeline may introduce additional failure modes.

6. **Determinism**: Seeds produce identical per-condition results; the outer seed
   is passed to the LLM provider as the model seed and does not create independent
   replicates.

7. **Confounded C1-vs-C0 comparison**: The difference is attributed to schema-aware
   generation, larger case count (51 vs 15), and a stronger oracle.

8. **Negative finding**: Adding more agents and feedback loops does not
   automatically improve detection.

## Limitations Note

All limitations are documented in `docs/limitations.md`. Key reiterated points:

- Single synthetic specification.
- Spec-derived oracle.
- Author-made fault catalogue.
- One mock API implementation.
- One LLM deployment (local Ollama only; C4–C8 unevaluated).
- Deterministic stability across seeds (one outcome per condition).
- Confounded C1-vs-C0 comparison.
- No inferential statistics.
- C4–C8 unevaluated.

## Results Data Location

Per-run experiment artifacts are stored in `artifacts/runs/<timestamp>/` (git-ignored).
The authoritative Phase 4 run is:

```
artifacts/runs/20261118T090640Z-phase4-final/
  C0_legacy/seed-1/condition_result.json
  C1_schema/seed-1/condition_result.json
  C2_single_llm/seed-1/condition_result.json
  C3_multi_llm/seed-1/condition_result.json
  summary.json
```

A curated, immutable subset of the deterministic evidence is preserved under
`artifacts/research_evidence/`. The earlier audit snapshot remains under
`artifacts/runs/20261117T171353Z-audit-final/` for historical reference.
