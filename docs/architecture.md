# Architecture

## Design goals

1. Keep every experiment local, inspectable, and reproducible.
2. Separate deterministic research infrastructure from optional LLM behavior.
3. Never present deterministic output as LLM output.
4. Make agent roles replaceable so ablations can be run from one orchestrator.
5. Preserve the original project files untouched.

## High-level flow

```text
OpenAPI/Swagger document
  -> SpecLoader (normalize)
  -> SpecResolver (schemas, parameters, auth, examples)
  -> DependencyGraph (operation relationships)
  -> SpecAnalyst (risk model)
  -> Planner (technique selection)
  -> Generator (deterministic and/or LLM cases)
  -> Validator (schema/path/step/capture checks)
  -> Repairer (optional deterministic basic repair or LLM repair)
  -> CodeRenderer (standalone pytest files)
  -> ExecutionEngine (loopback HTTP)
  -> Mock API (seeded state + injected fault)
  -> Oracle (status/schema/state/business rules)
  -> Metrics and charts
```

## Module map

| Path | Responsibility |
|---|---|
| `agenticapi/models.py` | Typed dataclasses for specs, plans, cases, executions, results, config |
| `agenticapi/config.py` | `Settings` and experiment configuration loading |
| `agenticapi/security.py` | Loopback enforcement, secret redaction, generated-code policy |
| `agenticapi/spec/resolver.py` | Resolve local schema references and operation metadata |
| `agenticapi/spec/loader.py` | Load OpenAPI 3.x and Swagger 2.0 into one `APISpec` |
| `agenticapi/spec/graph.py` | Build resource dependency graph |
| `agenticapi/spec/schema.py` | Schema examples, boundary values, and validation |
| `agenticapi/llm/provider.py` | Deterministic and OpenAI-compatible providers |
| `agenticapi/llm/gateway.py` | Structured output validation, retries, token/cost accounting |
| `agenticapi/llm/prompts.py` | Bounded prompts with explicit data-only framing |
| `agenticapi/agents/base.py` | `AgentContext`, traces, LLM role gating |
| `agenticapi/agents/spec_analyst.py` | Risk scores and optional LLM notes |
| `agenticapi/agents/planner.py` | Technique inference and plan construction |
| `agenticapi/agents/generator.py` | Deterministic builders and LLM case parsing |
| `agenticapi/agents/validator.py` | Case validity checks before execution |
| `agenticapi/agents/oracle.py` | Separate spec-derived expected-behavior evaluation (not an independent oracle) |
| `agenticapi/agents/repairer.py` | Basic deterministic repair and optional LLM repair |
| `agenticapi/agents/code_renderer.py` | Render and policy-check pytest artifacts |
| `agenticapi/agents/orchestrator.py` | Run a condition/seed and write artifacts |
| `agenticapi/execution/executor.py` | HTTP execution, auth, captures, serialization |
| `agenticapi/mock_api/store.py` | Seeded mutable shop state |
| `agenticapi/mock_api/server.py` | Local HTTP API, admin reset/fault/state endpoints |
| `agenticapi/evaluation/faults.py` | F01–F12 fault catalogue |
| `agenticapi/evaluation/fault_runner.py` | Clean/fault runs and detection calculation |
| `agenticapi/evaluation/metrics.py` | Pass and detection summaries |
| `agenticapi/evaluation/conditions.py` | C0–C8 conditions |
| `agenticapi/evaluation/baselines.py` | Legacy-style case construction |
| `agenticapi/evaluation/runner.py` | Multi-condition/seed experiment runner |
| `agenticapi/evaluation/charts.py` | Dependency-free SVG bar charts |
| `agenticapi/cli.py` | `check`, `conditions`, `mock`, `run` commands |

## Agent interface

All agents implement `BaseAgent.run(context, ...)`. `AgentContext` carries:

- the normalized spec and graph,
- `Settings`, `LLMGateway`, run directory and seed,
- `use_llm` and `llm_roles` so ablations can disable individual LLM roles,
- a trace list written to `traces.json`.

An agent does not contact the network directly. Execution is centralized in
`ExecutionEngine`; LLM access is centralized in `LLMGateway`. This keeps policy
checks and experiment accounting in one place.

## Plain and LLM modes

Deterministic conditions use `DeterministicProvider` and make no network calls. LLM
experiment conditions require `AGENTICAPI_LLM_API_KEY` and use
`OpenAICompatibleProvider`; otherwise the orchestrator marks the condition `BLOCKED`
and stops before generating cases. `Settings.llm_provider` is parsed but does not
currently select a provider, and `AGENTICAPI_LLM_PROVIDER` has no effect. A
test-only `FakeLLMProvider` verifies the integration path without claiming real LLM
results.

## Generated test artifacts

`CodeRenderer` writes one self-contained pytest file per case. It embeds request
data and uses only `requests`, `json`, `base64`, and `agenticapi`. The generated
source is parsed with `ast` and checked by `security.validate_generated_code`
before it is counted as valid. In an experiment, invalid artifacts are recorded and
excluded from execution.

## Condition handling

`Orchestrator.run_condition` resolves the condition specification and selects:

- legacy baseline generation with `oracle_mode="legacy"` (`status < 500`) for `C0`;
- deterministic generation and the full oracle for `C1` / `C1R`;
- `C2`: default plan plus one LLM generation call;
- `C3` / `C8`: LLM analysis, optional planning, generation, and optional repair,
  with deterministic validation/execution and the selected oracle;
- `C4`: `C3` with the default plan instead of the Planner;
- `C5`: `C3` without the validator gate (repair can still re-filter invalid cases);
- `C6` / `C7`: no repair; currently the same configuration.

All LLM conditions have a credential gate. Generated pytest artifacts are
materialized and policy-checked, but the experiment executes cases through
`ExecutionEngine`, not by running those files.

Every run writes analysis, plan, raw/executable cases, validation report, generated
tests, clean results, per-fault results, traces, and a `condition_result.json`.
