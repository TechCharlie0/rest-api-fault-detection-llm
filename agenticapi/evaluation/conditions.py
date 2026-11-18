"""Experimental conditions and ablation definitions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConditionSpec:
    condition_id: str
    description: str
    use_llm: bool = False
    use_planner: bool = True
    use_validator: bool = True
    use_repair: bool = False
    use_execution_feedback: bool = True
    use_faults: bool = True
    oracle_mode: str = "full"
    legacy: bool = False
    randomized: bool = False
    allow_fallback: bool = False


CONDITIONS: dict[str, ConditionSpec] = {
    "C0_legacy": ConditionSpec(
        condition_id="C0_legacy",
        description="Legacy-style single functional template per operation with a status<500 oracle.",
        use_planner=False,
        use_validator=False,
        use_repair=False,
        oracle_mode="legacy",
        legacy=True,
    ),
    "C1_schema": ConditionSpec(
        condition_id="C1_schema",
        description="Deterministic schema-aware planner, generator, validator, and spec oracle.",
        use_planner=True,
        use_validator=True,
        use_repair=False,
        oracle_mode="full",
    ),
    "C1R_randomized": ConditionSpec(
        condition_id="C1R_randomized",
        description="Deterministic schema-aware pipeline with seeded randomized values.",
        use_planner=True,
        use_validator=True,
        use_repair=False,
        oracle_mode="full",
        randomized=True,
    ),
    "C2_single_llm": ConditionSpec(
        condition_id="C2_single_llm",
        description="One LLM generation call with the default plan; deterministic validation and oracle.",
        use_llm=True,
        use_planner=False,
        use_validator=True,
        use_repair=False,
        oracle_mode="full",
    ),
    "C3_multi_llm": ConditionSpec(
        condition_id="C3_multi_llm",
        description="Mixed LLM/deterministic multi-agent pipeline with planning, validation, and repair.",
        use_llm=True,
        use_planner=True,
        use_validator=True,
        use_repair=True,
        oracle_mode="full",
    ),
    "C4_no_planner": ConditionSpec(
        condition_id="C4_no_planner",
        description="Multi-agent LLM ablation without a Planner agent.",
        use_llm=True,
        use_planner=False,
        use_validator=True,
        use_repair=True,
        oracle_mode="full",
    ),
    "C5_no_validator": ConditionSpec(
        condition_id="C5_no_validator",
        description="Multi-agent LLM ablation without the Validator gate; repair may still reject invalid cases.",
        use_llm=True,
        use_planner=True,
        use_validator=False,
        use_repair=True,
        oracle_mode="full",
    ),
    "C6_no_execution_feedback": ConditionSpec(
        condition_id="C6_no_execution_feedback",
        description="Execution-feedback ablation: repair is enabled but execution‑feedback‑driven replanning is disabled.",
        use_llm=True,
        use_planner=True,
        use_validator=True,
        use_repair=True,
        use_execution_feedback=False,
        oracle_mode="full",
    ),
    "C7_no_repair": ConditionSpec(
        condition_id="C7_no_repair",
        description="Repair ablation: execution‑feedback‑driven replanning is kept but repair is disabled.",
        use_llm=True,
        use_planner=True,
        use_validator=True,
        use_repair=False,
        use_execution_feedback=True,
        oracle_mode="full",
    ),
    "C8_status_oracle": ConditionSpec(
        condition_id="C8_status_oracle",
        description="Multi-agent LLM ablation with a status-only oracle (no schema checks).",
        use_llm=True,
        use_planner=True,
        use_validator=True,
        use_repair=True,
        oracle_mode="status",
    ),
}

DEFAULT_CONDITIONS = list(CONDITIONS)


def condition_by_id(condition_id: str) -> ConditionSpec:
    try:
        return CONDITIONS[condition_id]
    except KeyError as exc:
        known = ", ".join(CONDITIONS)
        raise KeyError(f"unknown condition {condition_id!r}; expected one of: {known}") from exc
