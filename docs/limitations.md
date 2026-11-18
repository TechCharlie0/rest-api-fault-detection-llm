# Limitations

This document discusses the actual limitations and threats to validity of the
research findings from the AgenticAPI project. Each limitation is numbered for
clear reference.

## 1. Single synthetic specification

The experiment uses one 15-operation OpenAPI specification (petstore/shop). The
spec includes operations across product, order, user, health, and inventory domains.
Results may not generalize to other APIs with different structures, scales, or
domains (e.g., banking, healthcare, microservices architectures). The 15-operation
size is relatively small, and larger or more complex APIs may produce different
fault detection rates.

## 2. Spec-derived oracle

The oracle uses the same specification as the generator. This means observed
detections may reflect spec conformance rather than independent human judgment.
The C1-vs-C0 comparison is further confounded by oracle strength differences (C1
uses a full status/schema/state/rules oracle, while C0 uses `status < 500`). It
is unclear whether detected faults are "real" or merely reflect spec compliance.

## 3. Author-made fault catalogue

The 12 injected faults are authored alongside the mock API. The catalogue may
favor schema-aware cases, creating a bias toward C1_schema detection. Faults
that are schema-rich (F02, F03, F10, F11) may be more readily detected by a
schema-aware pipeline, while faults that are more "logic-rich" may not be as well
represented. The catalogue does not claim statistical representativeness of
real-world API faults.

## 4. One mock API implementation

The local loopback mock API is a simplified representation of a real REST API.
Fault models, timing, concurrency, latency, and production-scale load are not
represented. Real APIs may have different error-handling patterns, authentication
mechanisms, and stateful behaviors that are not captured by the mock.

## 5. One LLM deployment

The deterministic conditions (C0_legacy, C1_schema, C1R_randomized) do not use
LLMs. The blocked conditions (C2–C8) have not been executed with real credentials,
so no claims about multi-agent LLM behavior are supported. Any claims about
single-agent or multi-agent LLM performance would be speculative. The research
team observed that when LLM credentials are available, the multi-agent pipeline
may produce more false positives without proportional recall gains, but this
observation requires further investigation with proper credentials and statistical
evaluation across multiple specs.

## 6. Deterministic stability across seeds

All five seeds (1–5) produce identical per-condition results. This is because the
generation prompt does not incorporate the outer seed; the generation is fully
deterministic given the same spec and seed. This means the experiment effectively
has one outcome per condition, not five independent replicates. No inferential
statistical test is appropriate with one outcome per condition. A future study
needs multiple specs, repeated stochastic runs, and confidence intervals.

## 7. Confounded C1-vs-C0 comparison

The difference between C1 and C0 is attributed to three factors operating
simultaneously:

- **Schema-aware generation**: C1 uses deterministic schema-aware planning, while
  C0 uses legacy template-based generation.
- **Case count**: C1 uses 51 generated cases per run, while C0 uses 15.
- **Oracle strength**: C1 uses a full status/schema/state/rules oracle, while C0
  uses `status < 500`.

The experiment does not isolate the effect of any single factor. It is unknown
whether the observed improvement is primarily due to schema-aware generation,
the larger case count, the stronger oracle, or some combination thereof.

## 8. No inferential statistics

With three to five deterministic seeds and one API, no inferential statistical
test is appropriate. A future study needs multiple specifications, repeated
stochastic runs, and confidence intervals to support statistical claims.

## 9. LLM conditions blocked

Without API key, conditions C2–C8 have not been executed. No claims about
single-agent or multi-agent LLM performance can be made. The code infrastructure
is designed to support these conditions when credentials are provided; the
blocking is a configuration state, not a design limitation.

## 10. Randomized values only affect functional bodies

C1R_randomized confirms that technique-specific cases (not randomized functional
values or query values) drive the detection behavior. This limits the
generalizability of findings to scenarios where functional value diversity matters
(e.g., boundary value analysis, randomized query parameter testing). The finding
does not extend to scenarios where value diversity is the primary detection driver.

## Summary

These limitations should be considered when interpreting the experimental results.
The strongest supported finding is that schema-aware deterministic pipeline (C1)
outperforms the conventional legacy baseline (C0) under the specific specification
and fault catalogue used. The generalizability of this finding to other APIs,
fault models, and LLM configurations is limited by the above threats to validity.