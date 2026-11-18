"""Specification analyst: deterministic risk model plus optional LLM notes."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from agenticapi.agents.base import AgentContext, BaseAgent
from agenticapi.spec.graph import graph_metrics

METHOD_WEIGHT = {"GET": 10, "POST": 30, "PUT": 25, "PATCH": 25, "DELETE": 40}
ALLOWED_AUTHZ = {"bearerAuth", "api_key", "petstore_auth"}


@dataclass
class SpecAnalysis:
    metrics: dict[str, object]
    risk_by_operation: dict[str, int] = field(default_factory=dict)
    protected_operations: list[str] = field(default_factory=list)
    workflows: list[list[str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    generated_by: str = "deterministic"


class SpecAnalystAgent(BaseAgent):
    """Scores operations using a documented, reproducible heuristic.

    risk = method baseline (GET 10, POST 30, PUT/PATCH 25, DELETE 40)
         + 15 if authentication is required
         + 10 if a request body exists
         + 2 * operation in-degree + 2 * operation out-degree
         + 15 if the operation appears in a declared workflow
         + 10 if the operation has a declared business rule
    Scores are clamped to [0, 100].  These weights are an engineering choice,
    not a claim of empirical validity.
    """

    def run(self, context: AgentContext) -> SpecAnalysis:
        started = time.perf_counter()
        rules = context.spec.extensions.get("x-agenticapi-business-rules", [])
        rule_operations = {
            str(rule.get("operation_id"))
            for rule in rules
            if isinstance(rule, dict) and rule.get("operation_id")
        }
        workflow_operations = {
            op_id for workflow in context.graph.workflows for op_id in workflow
        }
        risk: dict[str, int] = {}
        for op in context.spec.operations:
            score = METHOD_WEIGHT.get(op.method, 15)
            if op.requires_auth:
                score += 15
            if op.request_body is not None:
                score += 10
            score += 2 * context.graph.in_degree(op.operation_id)
            score += 2 * context.graph.out_degree(op.operation_id)
            if op.operation_id in workflow_operations:
                score += 15
            if op.operation_id in rule_operations:
                score += 10
            risk[op.operation_id] = max(0, min(100, score))
        analysis = SpecAnalysis(
            metrics=graph_metrics(context.spec, context.graph),
            risk_by_operation=risk,
            protected_operations=[op.operation_id for op in context.spec.operations if op.requires_auth],
            workflows=[list(workflow) for workflow in context.graph.workflows],
            notes=[
                "Deterministic risk model; weights are documented in SpecAnalystAgent.",
                "No LLM analysis was required for the deterministic baseline.",
            ],
            generated_by="deterministic",
        )
        if context.llm_allowed("analysis"):
            response = context.gateway.complete(
                "spec_analysis",
                {
                    "title": context.spec.title,
                    "version": context.spec.openapi_version,
                    "operations": [
                        {
                            "operation_id": op.operation_id,
                            "method": op.method,
                            "path": op.path,
                            "summary": op.summary,
                            "auth": op.requires_auth,
                        }
                        for op in context.spec.operations
                    ],
                    "business_rules": rules,
                },
            )
            if response.parsed and isinstance(response.parsed, dict):
                analysis.notes = [
                    str(note) for note in response.parsed.get("notes", []) if isinstance(note, str)
                ][:20]
                analysis.generated_by = f"llm:{response.provider}"
                context.trace(
                    self.name,
                    "llm_spec_analysis",
                    f"{len(analysis.notes)} notes",
                    started=started,
                    provider=response.provider,
                )
            else:
                analysis.notes.append(f"LLM analysis unavailable: {response.error}")
                context.trace(
                    self.name,
                    "llm_spec_analysis_failed",
                    response.error,
                    started=started,
                    provider=response.provider,
                    error=response.error,
                )
        else:
            context.trace(self.name, "deterministic_analysis", f"{len(risk)} operations")
        return analysis
