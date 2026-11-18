"""Repair invalid generated cases with an optional LLM or deterministic fixes."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from agenticapi.agents.base import AgentContext, BaseAgent
from agenticapi.agents.generator import GeneratorAgent
from agenticapi.agents.validator import ValidationReport, ValidatorAgent
from agenticapi.execution.serialization import case_to_dict
from agenticapi.models import Technique, TestCase

_POSITIVE_TECHNIQUES = {
    Technique.FUNCTIONAL,
    Technique.STATEFUL,
    Technique.BUSINESS_RULE,
}
_VALID_ASSERTION_KINDS = {"status", "schema", "json_path", "header", "same_as_step"}


@dataclass
class RepairReport:
    cases: list[TestCase] = field(default_factory=list)
    repaired: int = 0
    dropped: int = 0
    generated_by: str = "deterministic"
    notes: list[str] = field(default_factory=list)
    llm_repaired: int = 0
    llm_rejected: int = 0
    fallback_repaired: int = 0
    rejected: int = 0
    outcomes: list[dict[str, str]] = field(default_factory=list)
    rejected_cases: list[TestCase] = field(default_factory=list)


class RepairerAgent(BaseAgent):
    def run(self, context: AgentContext, report: ValidationReport) -> RepairReport:
        started = time.perf_counter()
        if not report.invalid:
            return RepairReport(cases=list(report.valid))
        if context.llm_allowed("repair"):
            return self._llm_repair(context, report, started)
        repaired: list[TestCase] = []
        dropped = 0
        outcomes: list[dict[str, str]] = []
        rejected_cases: list[TestCase] = []
        for case, errors in report.invalid:
            fixed = self._basic_fix(context, case, errors)
            if fixed is None:
                dropped += 1
                rejected_cases.append(case)
                outcomes.append(
                    {
                        "case_id": case.case_id,
                        "source": "rejected",
                        "note": "; ".join(errors),
                    }
                )
            else:
                repaired.append(fixed)
                outcomes.append(
                    {
                        "case_id": case.case_id,
                        "source": "deterministic",
                        "note": "expected status filled from spec",
                    }
                )
        validator = ValidatorAgent()
        validated = validator.run(context, list(report.valid) + repaired)
        notes = [
            "Deterministic repair only fills a missing expected status; structural "
            "errors are dropped rather than guessed."
        ]
        context.trace(
            self.name,
            "deterministic_repair",
            f"{len(validated.valid)} valid after repair",
            started=started,
        )
        return RepairReport(
            cases=validated.valid,
            repaired=max(0, len(validated.valid) - len(report.valid)),
            dropped=dropped,
            generated_by="deterministic",
            notes=notes,
            rejected=dropped,
            outcomes=outcomes,
            rejected_cases=rejected_cases,
        )

    def _llm_repair(
        self,
        context: AgentContext,
        report: ValidationReport,
        started: float,
    ) -> RepairReport:
        originals = {case.case_id: (case, errors) for case, errors in report.invalid}
        payload = {
            "invalid_cases": [
                {
                    "case": case_to_dict(case),
                    "errors": errors,
                    "operation_hint": self._operation_hint(context, case.operation_id),
                }
                for case, errors in report.invalid[:20]
            ],
            "known_operation_ids": [op.operation_id for op in context.spec.operations],
            "known_oracle_rules": [
                "quantity_le_stock",
                "order_status_transition",
                "delete_conflict",
                "idempotent_create",
            ],
            "repair_rules": [
                "Return the complete repaired case, not a partial patch.",
                "Every repaired case must include steps and expected_status.",
                "Preserve case_id, operation_id, technique, and description.",
                "Copy every original assertion unchanged into the repaired case.",
                "Do not weaken assertions or change expected results merely to make a failing test pass.",
            ],
        }
        response = context.gateway.complete("repair", payload)
        parsed_cases: list[TestCase] = []
        if response.parsed and isinstance(response.parsed, dict):
            parsed_cases = GeneratorAgent()._parse_cases(
                context, response.parsed.get("cases", [])
            )

        accepted: list[TestCase] = []
        outcomes: list[dict[str, str]] = []
        accepted_ids: set[str] = set()
        for candidate in parsed_cases:
            original_pair = originals.get(candidate.case_id)
            if original_pair is None:
                outcomes.append(
                    {
                        "case_id": candidate.case_id,
                        "source": "llm_rejected",
                        "note": "unknown case_id; not part of the invalid set",
                    }
                )
                continue
            if candidate.case_id in accepted_ids:
                outcomes.append(
                    {
                        "case_id": candidate.case_id,
                        "source": "llm_rejected",
                        "note": "duplicate repaired case_id",
                    }
                )
                continue
            original, _ = original_pair
            problems = self._repair_problems(context, original, candidate)
            if problems:
                outcomes.append(
                    {
                        "case_id": candidate.case_id,
                        "source": "llm_rejected",
                        "note": "; ".join(problems),
                    }
                )
                continue
            accepted.append(candidate)
            accepted_ids.add(candidate.case_id)
            outcomes.append(
                {
                    "case_id": candidate.case_id,
                    "source": "llm",
                    "note": "accepted by repair validation",
                }
            )

        rejected_ids = {
            outcome["case_id"]
            for outcome in outcomes
            if outcome["source"] == "llm_rejected"
        }
        for original, _ in report.invalid:
            if original.case_id in accepted_ids or original.case_id in rejected_ids:
                continue
            outcomes.append(
                {
                    "case_id": original.case_id,
                    "source": "llm_rejected",
                    "note": response.error or "no repaired case returned",
                }
            )

        fallback: list[TestCase] = []
        fallback_ids: set[str] = set()
        rejected_cases: list[TestCase] = []
        for original, errors in report.invalid:
            if original.case_id in accepted_ids:
                continue
            fixed = self._basic_fix(context, original, errors)
            if fixed is None:
                rejected_cases.append(original)
                outcomes.append(
                    {
                        "case_id": original.case_id,
                        "source": "rejected",
                        "note": "; ".join(errors),
                    }
                )
            else:
                fallback.append(fixed)
                fallback_ids.add(original.case_id)
                outcomes.append(
                    {
                        "case_id": original.case_id,
                        "source": "deterministic_fallback",
                        "note": "LLM repair missing or rejected; expected status filled from spec",
                    }
                )

        validator = ValidatorAgent()
        validated = validator.run(context, list(report.valid) + accepted + fallback)
        valid_ids = {case.case_id for case in validated.valid}
        llm_repaired = len(accepted_ids & valid_ids)
        fallback_repaired = len(fallback_ids & valid_ids)
        llm_rejected = max(0, len(report.invalid) - len(accepted_ids))
        rejected = sum(1 for outcome in outcomes if outcome["source"] == "rejected")
        dropped = max(0, len(report.invalid) - llm_repaired - fallback_repaired)
        notes = [
            f"LLM repair response ({response.provider}/{response.model}): "
            f"{response.error or 'parsed'}",
            "Only repaired cases that pass repair validation are retained.",
            f"LLM repaired={llm_repaired}, rejected LLM outputs={llm_rejected}, "
            f"deterministic fallbacks={fallback_repaired}, unrepaired={rejected}.",
        ]
        context.trace(
            self.name,
            "llm_repair",
            f"{len(validated.valid)} valid after repair",
            started=started,
            provider=response.provider,
            error=response.error,
        )
        return RepairReport(
            cases=validated.valid,
            repaired=llm_repaired + fallback_repaired,
            dropped=dropped,
            generated_by=f"llm:{response.provider}",
            notes=notes,
            llm_repaired=llm_repaired,
            llm_rejected=llm_rejected,
            fallback_repaired=fallback_repaired,
            rejected=rejected,
            outcomes=outcomes,
            rejected_cases=rejected_cases,
        )

    def _repair_problems(
        self,
        context: AgentContext,
        original: TestCase,
        candidate: TestCase,
    ) -> list[str]:
        problems: list[str] = []
        if candidate.case_id != original.case_id:
            problems.append("case_id changed")
        if candidate.operation_id != original.operation_id:
            problems.append("operation_id changed; test objective would move")
        if candidate.technique != original.technique:
            problems.append("technique changed; test objective would move")
        if not candidate.steps:
            problems.append("repaired case has no steps")
        check = ValidatorAgent().run(context, [candidate])
        if check.invalid:
            problems.extend(check.invalid[0][1])
        problems.extend(self._weakened_assertions(original, candidate))
        problems.extend(self._expected_status_problems(context, original, candidate))
        return problems

    @staticmethod
    def _weakened_assertions(original: TestCase, candidate: TestCase) -> list[str]:
        def key(value: Any) -> str:
            return json.dumps(value, sort_keys=True, default=str)

        def preserved(assertion: Any) -> bool:
            for item in candidate.assertions:
                if item.kind != assertion.kind:
                    continue
                if assertion.target and item.target != assertion.target:
                    continue
                if assertion.description and item.description != assertion.description:
                    continue
                if assertion.expected is not None and key(item.expected) != key(
                    assertion.expected
                ):
                    continue
                return True
            return False

        problems: list[str] = []
        for assertion in original.assertions:
            if assertion.kind not in _VALID_ASSERTION_KINDS:
                continue
            if not preserved(assertion):
                problems.append(
                    f"repair dropped or weakened assertion {assertion.kind!r}"
                )
        return problems

    @staticmethod
    def _expected_status_problems(
        context: AgentContext,
        original: TestCase,
        candidate: TestCase,
    ) -> list[str]:
        expected = candidate.expected_status
        if expected is None and candidate.steps:
            expected = candidate.steps[-1].expected_status
        if expected is None:
            return ["repaired case does not declare an expected status"]
        if not 100 <= expected <= 599:
            return [f"repaired case declares invalid expected status {expected}"]
        if original.technique in _POSITIVE_TECHNIQUES:
            documented = int(context.spec.operation(original.operation_id).success_status)
            if expected != documented:
                return [
                    f"expected status {expected} does not match documented success "
                    f"status {documented}"
                ]
        return []

    @staticmethod
    def _operation_hint(context: AgentContext, operation_id: str) -> dict[str, Any]:
        try:
            operation = context.spec.operation(operation_id)
        except KeyError:
            return {}
        return {
            "method": operation.method,
            "path": operation.path,
            "success_status": int(operation.success_status),
        }

    @staticmethod
    def _basic_fix(context: AgentContext, case: TestCase, errors: list[str]) -> TestCase | None:
        structural = [
            error
            for error in errors
            if "does not declare any expected status" not in error
        ]
        if structural:
            return None
        if case.expected_status is None and case.steps:
            try:
                case.expected_status = int(context.spec.operation(case.operation_id).success_status)
            except (KeyError, ValueError):
                return None
            if case.steps[-1].expected_status is None:
                case.steps[-1].expected_status = case.expected_status
        return case
