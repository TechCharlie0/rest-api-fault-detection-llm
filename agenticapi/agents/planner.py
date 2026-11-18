"""Planner: deterministic technique selection, optionally refined by an LLM."""

from __future__ import annotations

import time

from agenticapi.agents.base import AgentContext, BaseAgent
from agenticapi.agents.spec_analyst import SpecAnalysis
from agenticapi.models import Operation, Technique, TestPlan, TestPlanItem

TECHNIQUE_NAMES = {technique.value for technique in Technique}


def _extensions_for(context: AgentContext, operation_id: str) -> dict[str, object]:
    for op in context.spec.operations:
        if op.operation_id == operation_id:
            return op.extensions
    return {}


def _rule_operations(context: AgentContext) -> set[str]:
    rules = context.spec.extensions.get("x-agenticapi-business-rules", [])
    return {
        str(rule.get("operation_id"))
        for rule in rules
        if isinstance(rule, dict) and rule.get("operation_id")
    }


def _has_authz(op: Operation) -> bool:
    return bool(op.extensions.get("x-agenticapi-authz") or op.extensions.get("x-agenticapi-required-role"))


def _infer_techniques(context: AgentContext, op: Operation) -> list[Technique]:
    techniques: list[Technique] = [Technique.FUNCTIONAL]
    if op.query_parameters or op.path_parameters or op.request_body or op.form_parameters:
        techniques.append(Technique.NEGATIVE)
    if op.query_parameters or op.path_parameters or op.request_body:
        techniques.append(Technique.BOUNDARY)
    if op.requires_auth:
        techniques.append(Technique.AUTH)
    if _has_authz(op):
        techniques.append(Technique.AUTHZ)
    if op.operation_id in _rule_operations(context):
        rules = context.spec.extensions.get("x-agenticapi-business-rules", [])
        for rule in rules:
            if not isinstance(rule, dict) or rule.get("operation_id") != op.operation_id:
                continue
            if rule.get("oracle") == "idempotent_create":
                techniques.append(Technique.IDEMPOTENCY)
            elif rule.get("oracle") in {"quantity_le_stock", "order_status_transition", "delete_conflict"}:
                techniques.append(Technique.BUSINESS_RULE)
    if op.method in {"POST", "PUT", "PATCH", "DELETE"} and any(
        op.operation_id in workflow for workflow in context.graph.workflows
    ):
        techniques.append(Technique.STATEFUL)
    if op.method == "POST" and op.path.count("/") == 1:
        techniques.append(Technique.STATEFUL)
    declared = op.extensions.get("x-agenticapi-techniques")
    if isinstance(declared, list):
        for name in declared:
            try:
                techniques.append(Technique(str(name)))
            except ValueError:
                continue
    return list(dict.fromkeys(techniques))


class PlannerAgent(BaseAgent):
    @staticmethod
    def default_plan(context: AgentContext) -> TestPlan:
        return TestPlan(
            items=[
                TestPlanItem(
                    operation_id=op.operation_id,
                    techniques=list(Technique),
                    priority=0,
                    max_cases=context.config.max_cases_per_operation,
                    rationale="default plan (Planner agent disabled)",
                )
                for op in context.spec.operations
            ],
            generated_by="default",
        )

    def run(self, context: AgentContext, analysis: SpecAnalysis) -> TestPlan:
        started = time.perf_counter()
        items: list[TestPlanItem] = []
        for op in context.spec.operations:
            techniques = _infer_techniques(context, op)
            items.append(
                TestPlanItem(
                    operation_id=op.operation_id,
                    techniques=techniques,
                    priority=analysis.risk_by_operation.get(op.operation_id, 0),
                    max_cases=max(1, context.config.max_cases_per_operation),
                    rationale="deterministic heuristic from method, parameters, auth, graph degree, and declared rules",
                )
            )
        plan = TestPlan(items=items, generated_by="deterministic")
        if context.llm_allowed("planning"):
            response = context.gateway.complete(
                "planning",
                {
                    "operations": [
                        {
                            "operation_id": op.operation_id,
                            "method": op.method,
                            "path": op.path,
                            "summary": op.summary,
                            "parameters": [
                                {"name": p.name, "in": p.location, "required": p.required}
                                for p in op.parameters
                            ],
                            "auth": op.requires_auth,
                            "request_media_type": op.primary_media_type if op.request_body else None,
                        }
                        for op in context.spec.operations
                    ],
                    "allowed_techniques": sorted(TECHNIQUE_NAMES),
                    "business_rules": context.spec.extensions.get(
                        "x-agenticapi-business-rules", []
                    ),
                },
            )
            if response.parsed and isinstance(response.parsed, dict):
                known_ops = {op.operation_id for op in context.spec.operations}
                by_id = {item.operation_id: item for item in items}
                for raw in response.parsed.get("items", []):
                    if not isinstance(raw, dict):
                        continue
                    op_id = str(raw.get("operation_id", ""))
                    if op_id not in known_ops or op_id not in by_id:
                        continue
                    llm_techniques: list[Technique] = []
                    for name in raw.get("techniques", []):
                        try:
                            llm_techniques.append(Technique(str(name)))
                        except ValueError:
                            continue
                    if not llm_techniques:
                        continue
                    existing = by_id[op_id]
                    existing.techniques = list(
                        dict.fromkeys(existing.techniques + llm_techniques)
                    )
                    existing.priority = int(raw.get("priority", existing.priority) or existing.priority)
                    existing.max_cases = max(
                        1,
                        min(
                            int(raw.get("max_cases", existing.max_cases) or existing.max_cases),
                            context.config.max_cases_per_operation,
                        ),
                    )
                    existing.rationale = str(raw.get("rationale", existing.rationale))
                plan.generated_by = f"llm+deterministic:{response.provider}"
                context.trace(
                    self.name,
                    "llm_planning",
                    f"{len(plan.items)} items",
                    started=started,
                    provider=response.provider,
                )
            else:
                context.trace(
                    self.name,
                    "llm_planning_failed",
                    response.error,
                    started=started,
                    provider=response.provider,
                    error=response.error,
                )
        else:
            context.trace(self.name, "deterministic_planning", f"{len(items)} items")
        plan.items.sort(key=lambda item: (-item.priority, item.operation_id))
        return plan
