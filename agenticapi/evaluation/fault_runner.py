"""Run generated cases against each injected fault and record detection."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from agenticapi.evaluation.faults import all_faults, fault_by_id
from agenticapi.execution.executor import ExecutionEngine
from agenticapi.models import Fault, OracleResult, TestCase

if TYPE_CHECKING:
    from agenticapi.agents.base import AgentContext
    from agenticapi.agents.oracle import OracleAgent

_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _is_template(segment: str) -> bool:
    return segment.startswith("{") and segment.endswith("}")


def _path_matches(template: str, candidate: str) -> bool:
    template_parts = template.strip("/").split("/")
    candidate_parts = candidate.strip("/").split("/")
    if len(template_parts) != len(candidate_parts):
        return False
    for expected, actual in zip(template_parts, candidate_parts, strict=False):
        if expected == actual:
            continue
        if _is_template(expected) or _is_template(actual):
            continue
        return False
    return True


def case_touches(case: TestCase, fault: Fault) -> bool:
    for step in case.steps:
        if step.method.upper() != fault.method.upper():
            continue
        normalized = _VAR_RE.sub(lambda match: "{" + match.group(1) + "}", step.path)
        if _path_matches(fault.path, normalized):
            return True
    return False


def select_cases(cases: list[TestCase], fault_id: str) -> list[TestCase]:
    fault = fault_by_id(fault_id)
    return [case for case in cases if case_touches(case, fault)]


def run_fault_suite(
    context: AgentContext,
    engine: ExecutionEngine,
    oracle: OracleAgent,
    cases: list[TestCase],
    *,
    fault_ids: list[str] | None = None,
    oracle_mode: str = "full",
    all_cases: bool = False,
    records: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, list[OracleResult]]:
    """Run clean-selected or all cases under each eligible fault.

    ``all_cases`` is the research default: path-prefiltering hides faults whose
    observable stimulus is not expressed by an operation-id filter.  Every raw
    execution is written to ``records`` when a sink is supplied.
    """
    results: dict[str, list[OracleResult]] = {}
    selected_fault_ids = fault_ids or [fault.fault_id for fault in all_faults()]
    try:
        for fault_id in selected_fault_ids:
            fault = fault_by_id(fault_id)
            selected = list(cases) if all_cases else select_cases(cases, fault.fault_id)
            engine.set_fault(fault.fault_id)
            fault_results: list[OracleResult] = []
            for case in selected:
                record = engine.execute(case)
                outcome = oracle.evaluate(context, case, record, mode=oracle_mode)
                fault_results.append(outcome)
                if records is not None:
                    records.setdefault(fault.fault_id, []).append(
                        {
                            "case": case.to_dict(),
                            "record": record.to_dict(),
                            "oracle": outcome.to_dict(),
                        }
                    )
            results[fault.fault_id] = fault_results
    finally:
        engine.set_fault(None)
    return results
