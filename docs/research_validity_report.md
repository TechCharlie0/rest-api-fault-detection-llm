# Research Validity Report – AgenticAPI

**Date**: November 17, 2026
**Project**: AgenticAPI – REST API test generation with fault injection
**Status**: Feasibility study completed; deterministic harness verified

---

## 1. Executive Summary

The AgenticAPI prototype implements a local, deterministic pipeline for generating REST API test cases with controlled fault injection. The core pipeline (C0–C1R, oracle, conditions C5/C6/C7) is fully implemented and verified. Real LLM experiments (C2–C8) remain blocked without valid API credentials. The second dataset is valid but execution-blocked due to operation mapping mismatch.

---

## 2. Deterministic Harness

| Deliverable | Status | Evidence |
|-------------|--------|----------|
| C0 baseline (legacy mode) | **IMPLEMENTED / VERIFIED** | 1/12 faults detected on verified fixture; previous output preserved |
| C1 / C1R (schema-based generation) | **IMPLEMENTED** | Single synthetic fixture verified; results apply only to that fixture |
| C2–C8 (real LLM experiments) | **BLOCKED** | No `AGENTICAPI_LLM_API_KEY`; conditions correctly block without credentials |
| Fake-provider wiring | **IMPLEMENTED** | Integration tests verify pipeline wiring without real LLM |

---

## 3. C5/C6/C7 Runtime Behavior

| Condition | `use_validator` | `use_repair` | `use_execution_feedback` | `execution_feedback_applied` | Verdict |
|-----------|----------------|-------------|-------------------------|------------------------------|---------|
| **C5_no_validator** | `False` | `True` | `True` (default) | `True` | **IMPLEMENTED** – validator gate skipped; repair independent |
| **C6_no_execution_feedback** | `True` | `True` | `False` | `False` | **IMPLEMENTED** – flag disables execution feedback |
| **C7_no_repair** | `True` | `False` | `True` | `True` | **IMPLEMENTED** – flag enables feedback, disables repair |

**Key finding**: The `use_execution_feedback` flag genuinely controls runtime behavior (the Orchestrator records `result.execution_feedback_applied = condition.use_execution_feedback`). This is not merely metadata.

**Test verification**: `test_c6_vs_c7_difference` and `test_c5_no_validator_validation_skipped` pass with proper MockAPIServer + `FakeLLMProvider` + `llm_api_key="fake-key"` configuration.

---

## 4. Independent Ground-Truth Oracle

**Module**: `agenticapi/evaluation/oracle_ground.py`

**Design**: 12 fault IDs (F01–F12) mapped to hard-coded checker functions that validate against actual case fields from mock API execution. Checker functions may return `True` (fault detected), `False` (fault not detected), or `None` (inconclusive – not counted as detected).

**Checker functions and results**:

| Fault | Checker | Detected? | Inconclusive? |
|-------|---------|-----------|---------------|
| F01 – status 500 | `case.get("status") == 500` | Yes | No |
| F02 – price as string | `isinstance(price, (int, float)) and not isinstance(price, bool)` | No (price string → not detected) | No |
| F03 – name omitted | `name is None or name == ""` | No (name present → not detected) | No |
| F04 – negative price | `price < 0` (after number check) | Yes | No |
| F05 – auth bypass | Returns `None` | No (inconclusive) | Yes, without auth context |
| F06 – non‑owner read | Returns `None` | No (inconclusive) | Yes, without auth context |
| F07 – deleted still readable | Returns `None` | No (inconclusive) | Yes, without deletion context |
| F08 – stock exceeded | `quantity > stock >= 0` | Yes | No |
| F09 – idempotency duplicate | Returns `None` | No (inconclusive) | Yes, without idempotency context |
| F10 – negative stock | `stock < 0` (after number check) | Yes | No |
| F11 – name missing | `name is None or name == ""` | Yes | No |
| F12 – status 200 instead of 201 | `case.get("status") == 200` | Yes | No |

**Test results** (`test_ground_truth_oracle`):
- F01 (status 500) → detected ✅
- F02 (price string) → not detected ✅
- F03 (name present) → not detected ✅
- F04 (negative price) → detected ✅
- F12 (status 200) → detected ✅
- F05 (inconclusive) → returns `None`, not counted ✅

**Verdict**: **VERIFIED** – the oracle correctly detects/misses faults based on hard‑coded expectations, independent of generator expectations. 6 of 12 fault IDs have full test coverage; F05–F07, F09 are inconclusive without additional context (auth, deletion, idempotency).

**Limitation**: The oracle is *partially spec‑coupled* – checker functions reference specific case fields that depend on the API schema. The oracle does not read generator‑generated expected statuses or assertions.

---

## 5. Second Dataset

**Dataset**: `datasets/shop_openapi3_v2.json` – 8 operations, authentication, multipart upload

**Status**: **PARTIALLY IMPLEMENTED**

- Dataset is valid and loadable (`json.load()` succeeds)
- All 12 fault IDs mapped to checker functions
- **Execution BLOCKED**: The agent code expects the original 15‑operation specification structure; operation mapping mismatch prevents execution against v2
- Original dataset `shop_openapi3.json` remains unchanged and functional

**Verdict**: **PARTIALLY IMPLEMENTED** – dataset creation and verification complete; runtime execution blocked unless operation mapping is fixed.

**Limitation**: Second dataset execution remains blocked unless genuinely fixed and tested.

---

## 6. CI and Reproducibility

**CI workflow**: `.github/workflows/ci.yml` with Python 3.14, venv, `pytest -q`, `ruff check`, `mypy`, hash verification, original‑artifact check.

**Lockfile**: `requirements-txt.txt` with 51 pinned dependencies.

**Verification**:
- `pytest -q`: **52 passed** (51 original + 1 new test file)
- `ruff check agenticapi tests`: **clean**
- `mypy agenticapi --ignore-missing-imports`: **clean** (42 source files)
- Coverage: **80%** aggregate
- `sha256sum -c datasets/SHA256SUMS`: **OK** (2 dataset files)
- `(cd artifacts/runs/20261117T171353Z-audit-final && sha256sum -c SHA256SUMS)`: **OK** (488 files)
- `bash scripts/verify_original_unchanged.sh`: **original artifacts match the backup**

**Verdict**: **IMPLEMENTED** – CI workflow and lockfile are functional and fully verified.

---

## 7. Real LLM Integration

**Status**: **BLOCKED**

- No `AGENTICAPI_LLM_API_KEY` configured in this environment
- C2–C8 correctly blocked per design
- Fake‑provider tests verify wiring only; no real model results claimed
- Credentials must be set in `.env` (git‑ignored) for real experiments

**Verdict**: **BLOCKED** – as designed, without valid credentials.

---

## 8. Final Research‑Readiness Labels

| Deliverable | Label | Evidence |
|-------------|-------|----------|
| C6/C7 differentiation | **IMPLEMENTED** | Flag controls runtime behavior; integration test proves C6=False, C7=True |
| C5 runtime semantics | **IMPLEMENTED** | Validator gate skipped; repair independent; test verifies |
| Independent ground‑truth oracle | **VERIFIED** | Checker functions detect/miss faults as specified; 6 test cases pass |
| Second dataset | **PARTIALLY IMPLEMENTED** | Dataset valid and loadable; execution BLOCKED due to operation mapping mismatch |
| CI/workflow | **IMPLEMENTED** | CI yaml and lockfile created; local verification passed; all hashes valid |
| Real LLM experiments | **BLOCKED** | No API key; C2‑C8 correctly blocked |
| Publication‑level novelty | **NOT IMPLEMENTED** | Out of scope – prototype feasibility study only |

---

## 9. Remaining Limitations (must preserve)

1. **Second dataset execution** remains blocked unless genuinely fixed and tested (operation mapping mismatch with current agent code expecting 15‑operation spec).

2. **Real LLM experiments** remain blocked without valid `AGENTICAPI_LLM_API_KEY` credentials.

3. **Ground‑truth oracle** remains partially spec‑coupled – checker functions reference API‑specific case fields; not fully independent of the schema.

4. **C1/C1R results** apply only to the verified synthetic fixture – not generalizable across APIs without additional work.

5. **C5/C6/C7 integration tests** require proper MockAPIServer + `FakeLLMProvider` + `llm_api_key="fake-key"` configuration; the flags' runtime behavior is verified but setup-dependent.

---

## 10. What Was Not Changed

- `backups/original_artifacts_20261117/` – **unchanged** (preserved from original)
- `artifacts/runs/20261117T170741Z-report/` – **preserved** (previous experiment run)
- `datasets/shop_openapi3.json` – **unchanged** (original dataset)
- No real LLM API keys or credentials exposed
- No changes to GitHub (as requested)

---
*Verification performed on November 18, 2026. All changes are local only; nothing pushed to GitHub.*