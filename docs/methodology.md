# Research Methodology

This document explains the research methodology and experimental conditions used
in the AgenticAPI project.

## Provenance

Condition design is current. Reported outcomes are from the authoritative Phase 4
execution (`artifacts/runs/20261118T090640Z-phase4-final`, seeds 1–5) plus the
verified three-seed default configuration for `C1R_randomized`. The historical
audit snapshot (`artifacts/runs/20261117T171353Z-audit-final`, prior revision)
reported 12/12 for `C1_schema`/`C1R_randomized`; those values are superseded by
the current implementation's 10/12 and are retained only as preserved history.

## Research Objective

To empirically evaluate whether feedback-driven multi-agent Large Language Model
systems can improve REST API fault detection compared with conventional testing,
schema-based testing, and single-agent LLM testing.

## Research Questions

| RQ | Question |
|---|---|
| **RQ1** | Does schema-aware deterministic pipeline (`C1`) detect more injected faults
   than a legacy template baseline (`C0_legacy`), when case count and oracle strength
   are held constant? |
| **RQ2** | Does adding seeded randomized request values (`C1R_randomized`) affect
   clean-pass reliability or expose additional boundary/value faults? |
| **RQ3** | Does decomposing the testing pipeline into independent planning,
   generation, validation, and repair roles (`C2_single_llm`, `C3_multi_llm`)
   improve fault detection or case validity compared with a single monolithic
   LLM call? |
| **RQ4** | What is the impact of removing individual pipeline components
   (planner, validator, repair, schema oracle) on fault detection rates,
   precision, recall, and F1-score? |
| **RQ5** | Under what conditions does increasing the number of agents and adding
   feedback loops improve or degrade REST API fault detection performance? |

## Hypotheses

| Hypothesis | Statement | Status |
|---|---|---|
| **H1** | A schema-aware deterministic pipeline (`C1`) detects more injected faults
   than a legacy template baseline (`C0_legacy`). The present comparison confounds
   generation with case count and oracle strength, so it is an operational check,
   not a clean test of H1. | Not independently testable (confounded) |
| **H2** | Adding seeded randomized request values (`C1R_randomized`) does not reduce
   clean-pass reliability and may expose additional boundary/value faults. | Supported: C1R matched C1 (10/12, F1 = 1.0) |
| **H3** | Independent planning, validation, and repair roles improve case validity
   and recovery when an LLM is the generator (`C2`, `C3`). | Partially evaluated in Phase 4 (local Ollama): C2 F1 = 0.8333, C3 F1 = 0.4706 |
| **H4** | Removing planning, validation, execution feedback, repair, or schema oracle
   checks degrades detection or reliability (`C4`–`C8`). | Not evaluated (`C4`–`C8` untested) |

## Experimental Conditions

| ID | Planner | Generator | Validator | Repair | Oracle | Purpose |
|---|---|---|---|---|---|---|
| `C0_legacy` | none | legacy template | no | no | `status < 500` | baseline |
| `C1_schema` | deterministic | deterministic | yes | no | status/schema/state/rules | main deterministic condition |
| `C1R_randomized` | deterministic | deterministic + seeded functional values | yes | no | same as C1 | value randomization control |
| `C2_single_llm` | default plan | LLM | yes (deterministic) | no | same as C1 | single LLM generation call |
| `C3_multi_llm` | LLM | LLM | yes (deterministic) | LLM optional | same as C1 | mixed LLM/deterministic multi-agent |
| `C4_no_planner` | default plan | LLM | yes (deterministic) | LLM optional | same as C1 | planner ablation |
| `C5_no_validator` | LLM | LLM | no gate; repair may re-filter | LLM optional | same as C1 | validation-gate ablation |
| `C6_no_execution_feedback` | LLM | LLM | yes (deterministic) | no | same as C1 | currently identical to C7 |
| `C7_no_repair` | LLM | LLM | yes (deterministic) | no | same as C1 | repair ablation |
| `C8_status_oracle` | LLM | LLM | yes (deterministic) | LLM optional | status only | oracle ablation |

## Seed Behavior and Determinism

- The default configuration uses three seeds (1, 2, 3); the Phase 4 experiment
  used five seeds (1–5).
- All seeds produce identical per-condition results.
- The outer seed does not create independent replicates; it is passed to the LLM
  provider as the model seed.
- No inferential statistical tests are applied or warranted given identical
  per-condition outcomes.

## Procedure

1. Load and normalize the local OpenAPI 3 document.
2. Build the operation graph.
3. Run each condition for the configured seeds (1–3 by default; 1–5 in Phase 4).
4. Execute all valid cases against a clean seeded mock API.
5. Reset state and inject each fault independently.
6. Record failures per fault and compute detection.
7. Write per-run JSON and aggregate CSV/SVG summaries.

## Metrics

- **Clean pass rate**: fraction of generated cases that pass on the unmodified mock
  API. Higher is better.
- **Fault detection rate**: fraction of the twelve injected faults for which at
  least one case fails. Higher is better.
- **Missed faults**: fault IDs with no failing case.
- **Case validity**: fraction of generated cases accepted by the validator.
- **LLM calls / tokens / estimated cost**: recorded per condition when a real
  provider is used.
- **Duration**: wall-clock run time per condition/seed.

## Analysis Plan

Descriptive statistics are reported: mean clean pass rate and mean fault detection
rate across seeds. With three to five deterministic seeds and one API, no inferential
statistical test is appropriate. A future study needs multiple specs, repeated
stochastic runs, and confidence intervals.

## Fault Catalogue

The local mock API supports twelve independently selectable faults:

| ID | Fault | Primary expected signal |
|---|---|---|
| F01 | `GET /products/p1` returns HTTP 500 | status |
| F02 | `GET /products/p1` returns `price` as a string | schema |
| F03 | `GET /products/p1` omits required `name` | schema |
| F04 | `POST /products` accepts a negative price | boundary |
| F05 | `GET /orders` allows a missing token | auth |
| F06 | `GET /orders/o1` allows a non-owner | authz |
| F07 | Deleted product remains readable | state |
| F08 | `POST /orders` accepts quantity above stock | business rule |
| F09 | Duplicate `Idempotency-Key` creates another order | idempotency |
| F10 | `GET /products/p1` returns `stock=-1` | schema/boundary |
| F11 | `POST /products` accepts a missing name | schema/validation |
| F12 | `POST /products` returns 200 instead of 201 | status |

Faults are injected through the mock API's admin endpoint and are never enabled
against a public service.

## Threats to Validity

- Single synthetic 15-operation spec and one mock implementation.
- Fault catalogue is authored alongside the mock and may favor schema-aware cases.
- The oracle uses the same specification as the generator, so it is spec-derived,
  not a fully independent human oracle.
- C0 vs C1 confounds case count, technique coverage, and oracle strength.
- `C1R` randomizes only functional bodies/query values; most technique cases are
  unchanged.
- C2 uses the default plan, not the deterministic Planner.
- C5 removes the validator gate, but LLM repair can still reject invalid cases.
- C6 and C7 currently compile to the same condition.
- Deterministic conditions are stable across seeds by construction.
- In the default configuration LLM conditions are blocked; Phase 4 evaluated only
  C2 and C3 with a local model, so C4–C8 remain untested and no broad claim about
  agentic LLM benefit is supported.
- Generated cases are judged by machine, not by external developers.