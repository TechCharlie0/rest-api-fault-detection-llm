"""Baseline case generators used by the legacy condition."""

from __future__ import annotations

from agenticapi.agents.base import AgentContext
from agenticapi.agents.generator import GeneratorAgent
from agenticapi.models import Technique, TestCase, TestPlan, TestPlanItem


def legacy_cases(context: AgentContext) -> list[TestCase]:
    """One functional template per operation, matching the old project's scope.

    The label "legacy" refers to the evaluation style (one happy-path request
    per operation and a status<500 oracle), not to a byte-for-byte copy of the
    old generator.
    """
    plan = TestPlan(
        items=[
            TestPlanItem(
                operation_id=op.operation_id,
                techniques=[Technique.FUNCTIONAL],
                priority=0,
                max_cases=1,
                rationale="legacy happy-path template",
            )
            for op in context.spec.operations
        ],
        generated_by="legacy_template",
    )
    return GeneratorAgent().run(context, plan)
