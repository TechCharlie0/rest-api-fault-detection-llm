# Research Evidence Directory

This directory contains essential evidence from the completed experiments in the
AgenticAPI research project. It is designed so that Professor Lin Tan can inspect
the actual experiment results from GitHub.

## Completed Experiments

The following three conditions were fully executed with deterministic seeds:

### C0_legacy (seed-1)
- **Source**: `artifacts/runs/20261117T171353Z-audit-final/C0_legacy/seed-1/`
- **Metrics**: fault_detection_rate=0.083 (1/12 faults detected), F1=0.333
- **Detected faults**: ['F01'] (HTTP 500 on GET /products/p1)
- **Missed faults**: ['F02', 'F03', 'F04', 'F05', 'F06', 'F07', 'F08', 'F09', 'F10', 'F11', 'F12']
- **Clean pass rate**: 1.00 (all 15 generated cases pass on unmodified mock API)
- **Oracle**: `status < 500`
- **Cases generated**: 15

### C1_schema (seed-1)
- **Source**: `artifacts/runs/20261117T171353Z-audit-final/C1_schema/seed-1/`
- **Metrics**: fault_detection_rate=1.000 (12/12 faults detected), F1=1.000
- **Detected faults**: ['F01', 'F02', 'F03', 'F04', 'F05', 'F06', 'F07', 'F08', 'F09', 'F10', 'F11', 'F12']
- **Missed faults**: none
- **Clean pass rate**: 1.00 (all 51 generated cases pass on unmodified mock API)
- **Oracle**: status/schema/state/rules
- **Cases generated**: 51

### C1R_randomized (seed-1)
- **Source**: `artifacts/runs/20261117T171353Z-audit-final/C1R_randomized/seed-1/`
- **Metrics**: fault_detection_rate=1.000 (12/12 faults detected), F1=1.000
- **Detected faults**: ['F01', 'F02', 'F03', 'F04', 'F05', 'F06', 'F07', 'F08', 'F09', 'F10', 'F11', 'F12']
- **Missed faults**: none
- **Clean pass rate**: 1.00 (all 51 generated cases pass on unmodified mock API)
- **Oracle**: same as C1_schema
- **Cases generated**: 51

## Blocked Experiments

The following conditions remain blocked without LLM API credentials:

- **C2_single_llm**: single LLM generation call — BLOCKED
- **C3_multi_llm**: mixed LLM/deterministic multi-agent pipeline — BLOCKED
- **C4_no_planner**: C3 without Planner — BLOCKED
- **C5_no_validator**: C3 without Validator gate — BLOCKED
- **C6_no_execution_feedback**: no repair — BLOCKED
- **C7_no_repair**: no LLM repair — BLOCKED
- **C8_status_oracle**: status-only oracle — BLOCKED

## Evidence Files

| File | Description |
|---|---|
| `C0_legacy-condition_result.json` | Full metrics, fault-level matrix (TP/FP/FN/TN), detected/ missed faults for C0_legacy |
| `C1_schema-condition_result.json` | Full metrics, fault-level matrix, all 12 faults detected for C1_schema |
| `C1R_randomized-condition_result.json` | Full metrics, fault-level matrix, all 12 faults detected for C1R_randomized |
| `C0_legacy-traces.json` | Execution traces showing per-case outcomes for C0_legacy |
| `C1_schema-traces.json` | Execution traces for C1_schema |
| `C1R_randomized-traces.json` | Execution traces for C1R_randomized |
| `C0_legacy-generated_test.py` | Representative generated pytest test file (create_order__functional.py) |
| `C0_legacy-generated_test2.py` | Another representative generated test (create_product__functional.py) |
| `C1_schema-generated_test.py` | Representative generated test with auth oracle (create_order__auth.py) |
| `C1_schema-generated_test2.py` | Another representative generated test (list_my_orders__auth.py) |
| `aggregate_summary.json` | Aggregate experiment summary across all conditions and seeds |
| `experiment_config.json` | Experiment configuration (conditions, seeds, settings) |
| `shop_openapi3.json` | Primary OpenAPI 3.0 dataset (15 operations, 12 faults) |
| `petstore_swagger2.json` | Secondary Swagger 2.0 dataset |
| `SHA256SUMS` | SHA-256 verification file: computed SHA-256 matches `4a1d500a6203521748be0972bd78505bcd4483fb252c475f0c583e386941f74b` |

## SHA-256 Dataset Verification

```
computed: 4a1d500a6203521748be0972bd78505bcd4483fb252c475f0c583e386941f74b
expected: 4a1d500a6203521748be0972bd78505bcd4483fb252c475f0c583e386941f74b
status: PASS
```

## How Evidence Relates to Reported Metrics

- **condition_result.json**: Contains the authoritative `fault_level_matrix` (tp/fp/fn/tn),
  `precision`, `recall`, `f1-score`, `accuracy`, and `opportunity_faults`. All reported
  metrics in the README and docs/results.md are computed from this file.

- **traces.json**: Shows per-case execution outcomes (PASS/FAIL/ERROR), useful for
  understanding which specific cases triggered faults.

- **Generated test files**: Self-contained pytest test files that were executed against
  the local mock API. Each file tests one operation and includes request data.

- **aggregate_summary.json**: Contains cross-condition summaries (fault detection rates,
  pass rates, fault categories).

- **shop_openapi3.json + SHA256SUMS**: The primary specification used in all experiments.
  The SHA-256 hash was verified against the expected value before experiments began.

## Relation to GitHub Repository

- This directory is NOT tracked by Git (see .gitignore), but has been made available
  separately so the professor can inspect the evidence without Git LFS complications.
- The original `artifacts/runs/` directory remains git-ignored and unchanged.
- All experiment execution was done with Python 3.12, Qwen2.5:1.5B via Ollama,
  and a local loopback mock API on port 8765.
- Conditions C2–C8 are blocked without LLM API keys; no results are claimed for these.
