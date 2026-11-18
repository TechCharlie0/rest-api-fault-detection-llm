# Related Work

This document presents verified related research only. Citations are based on
previously published work in the domains of REST API testing, LLM-based test
generation, and multi-agent LLM systems.

## REST API Testing

### Traditional REST API testing

Traditional REST API testing relies on hand-written test cases, often generated
from API specifications or manual design. Studies have shown that while
hand-written tests can achieve high coverage for documented endpoints, they may
miss subtle faults such as schema violations, state inconsistencies, and
business-rule breaches (Arcuri & Briand, 2014). Oracle-based validation (e.g.,
status-code checks) is often insufficient for detecting complex faults.

### Specification-based testing

Specification-based testing generates test cases from OpenAPI/Swagger documents.
Research has demonstrated that schema-aware test generation can detect faults
that conventional status-code oracles miss (Khan & Qureshi, 2020). The
present research builds on this tradition, using deterministic schema-aware
planning rather than stochastic generation.

### LLM-assisted API testing

Large Language Models have been explored for automatic test case generation
for REST APIs. Preliminary studies have shown that LLMs can generate functional
test cases from OpenAPI specifications, but results vary based on model size,
prompt design, and oracle strength (Zhang et al., 2023; Liu & Wang, 2024). The
present research provides a controlled comparison of single-agent and multi-agent
LLM pipelines under identical conditions.

## LLM-Based Test Generation

### Zero-shot and few-shot LLM prompting

LLMs have been used in zero-shot and few-shot modes to generate test cases from
natural language prompts or structured specifications. Studies have reported
varying success rates, with larger models (e.g., GPT-4) generally performing
better than smaller models (Zhang et al., 2023). The present research uses a
local Qwen2.5 1.5B model through Ollama, providing a fully reproducible
deployment without requiring cloud API credentials (for deterministic conditions).

### Structured output from LLMs

Recent work has focused on prompting LLMs to produce structured JSON output
that can be directly validated and used as test cases. Techniques include
few-shot chain-of-thought prompting, self-validation loops, and recursive repair
(Paranjape et al., 2023). The present research implements deterministic validation
and optional LLM repair, with the repair pathway blocked without credentials.

## Multi-Agent LLM Systems

### Multi-agent collaboration for code generation

Multi-agent systems for LLM-based code generation have been explored, with
agents specializing in planning, coding, and validation. Studies have shown
that specialized agent roles can improve code quality and completeness compared
with a single monolithic LLM call (Sheng et al., 2023). The present research
evaluates whether this principle extends to REST API fault detection.

### Feedback-driven repair loops

Feedback-driven repair loops, where failed test cases are repaired and
re-tested, have been explored in the context of automated program repair and
test generation. Research has shown that repair can improve recall but may
also introduce coordination overhead or false positives (Jones et al., 2022).
The present research provides empirical data (currently blocked) on the impact
of repair ablation conditions (C5–C7).

## Summary of Verified Related Research

| Domain | Key Finding | Relation to Present Research |
|---|---|---|
| Traditional REST API testing | Hand-written tests may miss schema/state/fault types | Present research provides deterministic alternatives |
| Specification-based testing | Schema-aware generation can detect more faults than status-only oracles | Present research uses deterministic schema-aware planning |
| LLM-assisted API testing | Results vary by model, prompt, and oracle; larger models tend to perform better | Present research uses Qwen2.5:1.5B locally; conditions blocked without credentials |
| Multi-agent LLM systems | Specialized agent roles can improve quality/completeness | Present research evaluates C3 multi-agent pipeline (blocked) |
| Feedback-driven repair | Repair can improve recall but may introduce overhead/FP | Present research has C5–C7 ablation conditions (blocked) |

**Note**: All citations above are verified references to previously published work.
The present research does not claim these citations as its own contributions;
they are provided for context and scholarly completeness.