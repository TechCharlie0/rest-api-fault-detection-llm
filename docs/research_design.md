# Research design

## Research question

Can schema-aware planning, diverse test techniques, execution feedback, and agent
decomposition improve detection of injected REST API faults compared with a
legacy-style one-template-per-operation baseline?

This is a feasibility study. It does **not** claim a new research contribution,
generalization across APIs, or publication readiness.

## Hypotheses

- **H1**: A schema-aware deterministic pipeline (`C1`) detects more injected faults
  than a legacy template baseline (`C0`). The present comparison confounds generation
  with case count and oracle strength, so it is an operational check, not a clean
  test of H1.
- **H2**: Adding seeded randomized request values (`C1R`) does not reduce clean-pass
  reliability and may expose additional boundary/value faults.
- **H3**: Independent planning, validation, and repair roles improve case validity
  and recovery when an LLM is the generator (`C2`, `C3`).
- **H4**: Removing planning, validation, execution feedback, repair, or schema
  oracle checks degrades detection or reliability (`C4`–`C8`).

H3 and H4 are **not yet testable** because no LLM credentials were available. C6 and
C7 currently have the same configuration, so C6 is not a distinct execution-feedback
ablation.

## Experimental conditions

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

## Fault catalogue

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

The primary comparison is `C1` vs `C0`. It is confounded: C0 uses 15 cases and a
`status < 500` oracle, while C1 uses 51 cases and a full status/schema/rule oracle.
`C1R` changes functional bodies/query values only. LLM conditions are reported only
when real credentials exist.

## Procedure

1. Load and normalize the local OpenAPI 3 document.
2. Build the operation graph.
3. Run each condition for seeds 1, 2, and 3.
4. Execute all valid cases against a clean seeded mock API.
5. Reset state and inject each fault independently.
6. Record failures per fault and compute detection.
7. Write per-run JSON and aggregate CSV/SVG summaries.

## Analysis plan

Descriptive statistics are reported: mean clean pass rate and mean fault detection
rate across seeds. With three deterministic seeds and one API, no inferential
statistical test is appropriate. A future study needs multiple specs, repeated
stochastic runs, and confidence intervals.

## Threats to validity

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
- LLM conditions are blocked, so no claim about agentic LLM benefit is supported.
- Generated cases are judged by machine, not by external developers.
