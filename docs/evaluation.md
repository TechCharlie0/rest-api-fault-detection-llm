# Evaluation

This document explains the metrics, ground truth, fault classification, and
evaluation methodology used in the AgenticAPI research project.

## Metric Definitions

The following metrics are computed from the fault-level matrix and differential
ground truth, as implemented in `agenticapi/evaluation/metrics.py`:

| Metric | Formula | Description |
|---|---|---|
| **True Positives (tp)** | Count of detected faults | A fault is detected when at least one test case that exercises the fault passes on the clean run and fails under the injected fault. |
| **False Positives (fp)** | Count of flagged-but-undetected faults | A fault has `clean_fail_case_ids` but is not in the detected set. |
| **False Negatives (fn)** | Count of missed faults | `fn = opportunity_count - tp`. |
| **True Negatives (tn)** | Count of non-detected faults | `tn = opportunity_count - fp`. |
| **Precision** | `tp / (tp + fp)` | Fraction of detected faults that are true faults. If `tp + fp = 0`, precision = 0.0. |
| **Recall** | `tp / (tp + fn)` | Fraction of actual faults that were detected. If `tp + fn = 0`, recall = 0.0. |
| **F1-score** | `2 * prec * rec / (prec + rec)` | Harmonic mean of precision and recall. If `prec + rec = 0`, F1 = 0.0. |
| **Accuracy** | `(tp + tn) / (tp + tn + fp + fn)` | Overall correctness ratio. If total = 0, accuracy = 0.0. |
| **Fault detection rate** | `tp / len(eligible)` | Fraction of eligible faults detected. |
| **Opportunity-adjusted detection** | `TP / opportunity_faults` | Per metric definitions: `TP / opportunity_faults = recall`. |
| **Clean pass rate** | `passing_cases / total_cases` | Fraction of generated cases that pass on the unmodified mock API. |
| **Case validity** | `accepted_cases / total_generated` | Fraction of generated cases accepted by the validator. |

### Fault-level matrix

The primary evaluation matrix contains four integer counts:

```
fp  fn
tn  tp
```

Populated as follows:

- `tp` = number of fault IDs in the detected set (`detected_faults`).
- `fp` = number of eligible fault IDs where `clean_fail_case_ids` is non-empty
  but the fault is not detected.
- `fn` = `opportunity_count - tp`, where `opportunity_count` = number of eligible
  faults minus `no_opportunity_faults`.
- `tn` = `opportunity_count - fp`.

### Opportunity-adjusted metric

Per the metric definitions in `metrics.py`:

> `TP / opportunity_faults = recall`

where `opportunity_faults` = the number of eligible faults (those not in
`no_opportunity_faults`). This means the opportunity-adjusted detection rate is
numerically equivalent to recall.

## Ground Truth and Fault Classification

### How ground truth is computed

1. Faults are injected through the mock API's admin endpoint.
2. A test case "exercises a fault" if it targets the operation and fault ID
   associated with the injection.
3. For each fault, the clean run is checked: if the case passes on the clean API,
   it is a "clean pass" opportunity for that fault.
4. Under the injected fault, the same case is re-executed: if it fails, the fault
   is detected.
5. A fault is "observed" when at least one case passes on the clean run and fails
   under the injected fault.
6. `ERROR` and `INVALID_TEST` outcomes are reported separately and are never counted
   as detections.

### Ground truth fields (from `metrics.py` summarize() return)

| Field | Description |
|---|---|
| `observed_faults` | Fault IDs where at least one clean-pass + fail-under-fault case pair exists. |
| `oracle_gaps` | Fault IDs where a clean-pass + fail pair exists but the oracle did not report detection. |
| `spurious_detections` | Fault IDs where the system detected a fault but the differential ground truth says no fault. |
| `agreements` | Fault IDs where the system's detection matches the differential ground truth. |

### Per-condition evaluation

Each condition's results are evaluated independently. The fault-level matrix and
related metrics are stored in `condition_result.json` per condition and seed.
Provenance validation ensures all condition-seed result files are valid before
analysis.

### LLM conditions

When LLM credentials are absent, conditions C2–C8 are marked `BLOCKED` and no
evaluation metrics are computed. When credentials are present, the same metric
computation pipeline applies, with the addition of LLM call counts, token usage,
and estimated cost reporting.

## Precision, Recall, F1-score

These three metrics form the primary evaluation triple:

- **Precision** measures: "Of the faults we flagged, how many are actual faults?"
- **Recall** measures: "Of the actual faults, how many did we detect?"
- **F1-score** harmonic mean: the balanced single-score summary of the above two.

In the executed deterministic conditions:

| Condition | Precision | Recall | F1-score |
|---|---|---|---|
| **C0_legacy** | 1.000 | 0.200 | 0.333 |
| **C1_schema** | 1.000 | 1.000 | 1.000 |
| **C1R_randomized** | 1.000 | 1.000 | 1.000 |

## Clean Pass Rate

The clean pass rate measures the fraction of generated test cases that pass when
executed against the unmodified (clean) mock API. A high clean pass rate
indicates that the generator and validator are producing syntactically correct
and semantically valid test cases.

| Condition | Clean pass rate |
|---|---|
| **C0_legacy** | 1.00 |
| **C1_schema** | 1.00 |
| **C1R_randomized** | 1.00 |

## Fault Detection Rate

The fault detection rate measures the fraction of the twelve injected faults for
which at least one generated test case fails. This is the primary success metric
for the research.

| Condition | Fault detection rate |
|---|---|
| **C0_legacy** | 0.083 (1/12) |
| **C1_schema** | 1.000 (12/12) |
| **C1R_randomized** | 1.000 (12/12) |

## Spurious Detections and Oracle Gaps

- **Spurious detection**: A fault is flagged as detected, but the differential
  ground truth says no fault exists (i.e., the case did not pass on the clean run
  or did not fail under the injected fault).
- **Oracle gap**: A fault has a clean-pass + fail-under-fault pair, but the oracle
  did not report it as detected (e.g., due to validation filtering).

Both are tracked in the evaluation output but are not included in the primary
TP/FP/FN/TN matrix.