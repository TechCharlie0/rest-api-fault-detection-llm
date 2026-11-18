# Documentation Center

Welcome to the AgenticAPI research project documentation. This center provides
access to all project documentation with a brief explanation of each document's
purpose and content.

## Document Index

| Document | Purpose | Key Contents |
|---|---|---|
| [research_design.md](./research_design.md) | Research motivation, gap, objectives, questions, methodology, validity considerations | Hypotheses H1–H4, experimental conditions C0–C8, fault catalogue, metrics, procedure, threats to validity |
| [architecture.md](./architecture.md) | Software architecture, component relationships, agent responsibilities, execution flow | Module map, agent interface, deterministic vs LLM modes, condition handling, generated test artifacts |
| [methodology.md](./methodology.md) | Research methodology and experimental conditions | Experimental design, condition table, seed behavior, determinism, procedure |
| [experimental_setup.md](./experimental_setup.md) | Software, model, datasets, configuration, dependencies, experiment setup | Dataset SHA-256, model/provider, conditions table, seeds, configuration files |
| [evaluation.md](./evaluation.md) | Metrics, ground truth, fault classification, precision, recall, F1-score, FP, FN | Metric definitions, fault-level matrix, ground truth computation, per-condition evaluation, LLM conditions |
| [results.md](./results.md) | Actual experimental results and their interpretation | Executive summary, detailed results table, per-condition details, observations |
| [limitations.md](./limitations.md) | Actual limitations and threats to validity | 10 numbered limitations with transparent discussion |
| [reproducibility.md](./reproducibility.md) | Complete instructions for another researcher to reproduce the experiments | Python version, virtual environment, Ollama + model, dependencies, check/run commands, artifact locations |
| [related_work.md](./related_work.md) | Verified related research only | Verified related research citations and brief descriptions |
| [repository_audit.md](./repository_audit.md) | Original architecture, audit findings, and changes made | Audit findings, original vs current state, changes made, files requiring approval |

## Navigation

Use the relative links above to navigate between documents. Each document is
self-contained but also cross-referenced where topics overlap.

---

## Document Purpose Summary

### research_design.md
Explains the research motivation, gap, objectives, research questions (RQ1–RQ5),
methodology, hypotheses (H1–H4), experimental conditions, fault catalogue, metrics,
procedure, and threats to validity.

### architecture.md
Describes the software architecture with a complete module map, agent interfaces,
deterministic vs LLM modes, condition handling, and generated test artifacts. Includes
component diagrams and data flow explanations.

### methodology.md
Documents the research methodology and experimental conditions, including the
condition table (C0–C8), seed behavior, determinism, fault catalogue, metrics, and
procedure. Serves as the methodological foundation for the experimental setup.

### experimental_setup.md
Lists the software, model, datasets, configuration, dependencies, and experiment
setup. Includes dataset SHA-256 verification, model/provider details, condition
table, seed behavior, and configuration file locations.

### evaluation.md
Explains the metrics used in the research (precision, recall, F1-score, accuracy,
fault detection rate, etc.), ground truth computation, fault classification,
per-condition evaluation, and LLM condition handling. Defines the fault-level matrix
and opportunity-adjusted metrics.

### results.md
 Presents the actual experimental results with executive summary, detailed tables,
 per-condition observations, and key findings. Honestly reports blocked conditions
 and confounded comparisons.

### limitations.md
Discusses the actual limitations and threats to validity of the research findings.
10 numbered limitations with transparent discussion of each.

### reproducibility.md
Provides complete instructions for another researcher to reproduce the experiments.
Includes Python version, virtual environment setup, Ollama + model installation,
dependencies, environment configuration, check/run commands, and artifact locations.

### related_work
Contains verified related research only. Citations and brief descriptions of
previously published work on REST API testing, LLM-based test generation, and
multi-agent LLM systems.

### repository_audit.md
Explains the original architecture, audit findings, and changes made during the
repository transformation. Documents what was changed, why, and what (if anything)
requires approval before finalization.