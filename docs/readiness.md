# Readiness assessment

**Audience:** Dr. Lin Tan
**Purpose:** honest assessment of the AgenticAPI prototype as a research work sample
**Date:** November 17, 2026

## Bottom line

This is a credible, working feasibility prototype and a useful demonstration of
research engineering. It is **not yet publication-ready** and it does **not** yet
provide evidence that LLM agents improve API test generation. The deterministic
harness works, is tested, and produces reproducible evidence; the LLM experiment is
implemented but blocked by the absence of credentials.

## What is strong

- End-to-end local pipeline: spec normalization, planning, generation, validation,
  rendering, execution, oracle, metrics, and artifacts.
- Controlled fault injection with twelve faults and an explicit detection metric.
- Honest baseline comparison: 1/12 faults for the faithful `status < 500` legacy
  baseline versus 12/12 for the deterministic pipeline on the local fixture. The
  comparison is confounded by case count and oracle strength, so it is a feasibility
  result, not a clean effect estimate.
- Separation between deterministic and LLM behavior, with `BLOCKED` status instead
  of fabricated LLM results.
- 51 passing tests, 80% aggregate coverage, clean `ruff` and `mypy`.
- Reproducible commands, dataset hashes, preserved original artifacts, and no
  external API calls.
- Documentation covers architecture, method, results, security, limitations, and
  contribution attribution.

## What is missing for a strong application or paper

1. **Real LLM evidence.** No key was available, so `C2`–`C8` are blocked. Without
   these runs, the central agentic claim is untested.
2. **More than one API.** One synthetic 15-operation shop spec is not enough to
   support generalization.
3. **A stronger independent oracle.** The current oracle is spec-derived. A second
   oracle (human-authored expectations or a different formal source) would reduce
   circularity.
4. **A real baseline and unconfounded comparison.** `C0` is a controlled
   reimplementation, and it differs from `C1` in case count (15 vs 51) and oracle
   strength as well as generation strategy.
5. **Statistical rigor.** Three deterministic seeds do not support confidence
   intervals; LLM runs need repeated stochastic trials and cost/latency reporting.
6. **Distinct ablations.** C6 and C7 currently compile to the same configuration;
   C5 removes the validator gate but repair can still re-filter invalid cases; C2
   uses the default plan rather than the Planner.
7. **External case-quality review.** Machine validation is not the same as developer
   judgment of readability and actionability.
8. **Packaging and CI.** The project runs locally but has no CI workflow, container,
   or pinned lockfile for a third party. Configured cost/repair limits are not fully
   enforced.

## Fit with Dr. Tan's projects

- **Project 2 (Agents and LLMs for SE: testing, bug/vulnerability detection, repair): high fit.**
  The prototype directly combines agent decomposition, test generation, fault
  detection, and repair.
- **Project 4: secondary fit.** There is a local execution and validation component,
  but no substantial program-analysis or vulnerability-discovery pipeline yet.

## Recommended two-week plan

| Priority | Task | Why |
|---|---|---|
| P0 | Differentiate C6/C7 and make the C5 gate semantics explicit | Avoid spending LLM budget on duplicate or mislabeled ablations |
| P0 | Configure a real LLM key and run `C2`–`C8` on the shop spec | Tests the central claim; produces real token/cost data |
| P0 | Add a second, structurally different OpenAPI spec and mock | Tests generalization beyond one fixture |
| P1 | Add an independent oracle or human-labeled expectations | Reduces spec-circularity threat |
| P1 | Repeat LLM runs (at least 5 trials per condition) and report distributions | Enables uncertainty reporting |
| P2 | Add CI and a lockfile | Makes the work sample easy to reproduce |
| P2 | Ask 2–3 developers to rate case quality | Adds external validity |

## Deadline risks

- The December 1, 2026 target is tight for a full LLM study plus a second API and
  human evaluation. A realistic submission can present the deterministic harness and
  a small LLM pilot, with clear `BLOCKED`/`PARTIAL` labels for what is unfinished.
- English proficiency scores were not available in this workspace. If required
  scores are missing, the Fall 2027 timeline may be at risk independently of the
  prototype.
- No Git history exists here, so contribution claims must be reviewed against the
  user's actual record before submission.

## Deliverable status labels

| Deliverable | Label | Evidence |
|---|---|---|
| Environment and original-artifact audit | IMPLEMENTED / VERIFIED | backup snapshot; unchanged-file diff |
| Architecture | IMPLEMENTED / VERIFIED | `docs/architecture.md` |
| Core models and configuration | IMPLEMENTED / VERIFIED | tests, mypy |
| OpenAPI/Swagger parsing | IMPLEMENTED / VERIFIED | `tests/test_spec.py` |
| Local mock API | IMPLEMENTED / VERIFIED | `tests/test_mock_api.py` |
| Fault catalogue F01–F12 | IMPLEMENTED / VERIFIED | fault runs |
| Legacy baseline | IMPLEMENTED / VERIFIED | faithful `status < 500` C0 audit run |
| Deterministic schema-aware pipeline | IMPLEMENTED / VERIFIED | C1/C1R results; confounded baseline comparison |
| Multi-agent LLM pipeline | PARTIALLY IMPLEMENTED / BLOCKED | fake-provider coordination test; no real key |
| LLM provider abstraction | IMPLEMENTED / VERIFIED (unit) | `tests/test_llm.py` |
| Validation and repair | IMPLEMENTED / VERIFIED (deterministic); ablations need work | pipeline tests; C5/C6 caveats |
| Execution and oracle | IMPLEMENTED / VERIFIED; oracle is spec-coupled | fault detection |
| Metrics, charts, CSV | IMPLEMENTED / VERIFIED | baseline artifacts |
| Real LLM experiments | BLOCKED | no credentials |
| Test suite and coverage | VERIFIED | 51 passed, 80% |
| Security checks | IMPLEMENTED / VERIFIED | secret scan, loopback policy, code policy |
| Documentation | IMPLEMENTED / VERIFIED (audit-corrected) | `docs/`, `docs/audit_report.md` |
| Publication-level novelty claim | NOT IMPLEMENTED | explicitly out of scope |

## Recommendation

Proceed, but frame the current artifact as a **working prototype and feasibility
study**, not as completed research. The fastest path to a credible application is to
fix the duplicate/mislabeled ablations, then run a small real LLM pilot plus a
second API, reported with explicit limitations and without overclaiming.
