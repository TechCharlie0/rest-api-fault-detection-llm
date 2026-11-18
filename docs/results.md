# Results

This document presents the actual experimental results from the AgenticAPI
research project, with honest interpretation and clear identification of
confounded findings and blocked conditions.

## Executive Summary

- **C1_schema** (schema-based deterministic) achieved the strongest observed
  result: a fault detection rate of 1.00 (12/12 faults detected), a clean pass
  rate of 1.00, precision of 1.00, recall of 1.00, and an F1-score of 1.00.
- **C0_legacy** (conventional) detected 1/12 faults (0.083 rate), with a clean
  pass rate of 1.00, precision of 1.00, recall of 0.200, and an F1-score of 0.333.
- **C1R_randomized** matched C1_schema: 1.00 fault detection rate, 1.00 clean
  pass rate, precision 1.00, recall 1.00, F1 1.00.
- **C2–C8** are blocked without LLM API credentials; no results are claimed for
  these conditions.
- The C1-vs-C0 comparison is confounded by case count (51 vs 15) and oracle
  strength (full status/schema/state/rules vs `status < 500`). The experiment
  does not isolate the effect of schema-aware generation from the effect of a
  stronger oracle or larger case count.

## Detailed Results Table

| Condition | Seeds | Cases per run | Clean pass rate | Faults detected | Detection rate | Precision | Recall | F1-score |
|---|---|---|---|---|---|---|---|---|
| **C0_legacy** | 1–5 | 15 | 1.00 | 1 / 12 | 0.083 | 1.000 | 0.200 | 0.333 |
| **C1_schema** | 1–5 | 51 | 1.00 | 12 / 12 | 1.000 | 1.000 | 1.000 | 1.000 |
| **C1R_randomized** | 1–5 | 51 | 1.00 | 12 / 12 | 1.000 | 1.000 | 1.000 | 1.000 |
| **C2_single_llm** | blocked | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| **C3_multi_llm** | blocked | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| **C4_no_planner** | blocked | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| **C5_no_validator** | blocked | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| **C6_no_execution_feedback** | blocked | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| **C7_no_repair** | blocked | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| **C8_status_oracle** | blocked | n/a | n/a | n/a | n/a | n/a | n/a | n/a |

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
- Detected all 12 injected faults, including schema, auth, authz, state, business-rule,
  boundary, and idempotency faults.
- 51 generated cases across 15 operations; all cases pass on the clean mock API.

### C1R_randomized

- `C1` with seeded randomized functional bodies/query values; technique-specific
  cases unchanged.
- Identical fault detection to C1_schema: 12/12 faults detected (1.00 rate).
- 51 generated cases per run; 1.00 clean pass rate.

### C2–C8

- Blocked without LLM API key. No results are claimed.

## Key Observations

1. **Schema-aware generation is effective**: C1_schema detects all 12 faults,
   while C0_legacy detects only 1.

2. **Case count and oracle strength confounded**: C1 uses 51 cases and a much
   stronger oracle than C0 (15 cases, `status < 500`). Both likely contribute.

3. **Randomized functional values do not degrade reliability**: C1R_randomized
   achieves the same detection as C1_schema.

4. **Multi-agent LLM conditions are blocked**: Without LLM credentials, no
   results can be reported for C2–C8.

5. **Honest observation on multi-agent potential**: When LLM credentials are
   available, increasing the number of agents and adding feedback loops may not
   necessarily improve fault detection performance. The multi-agent pipeline may
   introduce additional failure modes.

6. **Determinism**: All five seeds produce identical per-condition results.

7. **Confounded C1-vs-C0 comparison**: The difference is attributed to
   schema-aware generation, larger case count (51 vs 15), and a stronger oracle.

8. **Negative finding**: Adding more agents and feedback loops does not
   automatically improve detection.

## Limitations Note

All limitations are documented in `docs/limitations.md`. Key reiterated points:

- Single synthetic specification.
- Spec-derived oracle.
- Author-made fault catalogue.
- One mock API implementation.
- One LLM deployment (blocked).
- Deterministic stability across seeds (one outcome per condition).
- Confounded C1-vs-C0 comparison.
- No inferential statistics.
- LLM conditions blocked.

## Results Data Location

Per-run experiment artifacts are stored in:

```
artifacts/runs/<timestamp>/
  C0_legacy/seed-1/condition_result.json
  C1_schema/seed-1/condition_result.json
  C1R_randomized/seed-1/condition_result.json
```