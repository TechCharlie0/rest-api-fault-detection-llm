"""Runner aggregation, charts, and CLI smoke tests."""

from __future__ import annotations

import json
from pathlib import Path

from agenticapi.cli import main
from agenticapi.evaluation.charts import bar_chart
from agenticapi.evaluation.runner import aggregate
from agenticapi.models import ConditionResult, ConditionStatus, OracleResult, Outcome


def test_aggregate_and_chart(tmp_path: Path):
    results = [
        ConditionResult(
            condition="C1_schema",
            seed=1,
            status=ConditionStatus.COMPLETED,
            cases_generated=2,
            cases_valid=2,
            cases_executed=2,
            oracle_results=[
                OracleResult(case_id="a", outcome=Outcome.PASS),
                OracleResult(case_id="b", outcome=Outcome.FAIL, failure_kind="status"),
            ],
            metrics={"pass_rate": 0.5, "fault_detection_rate": 1.0, "faults_detected": 12},
            duration_seconds=0.1,
        )
    ]
    summary = aggregate(results, ["C1_schema"], [1])
    assert summary["conditions"]["C1_schema"]["pass_rate_mean"] == 0.5
    assert summary["conditions"]["C1_schema"]["fault_detection_rate_mean"] == 1.0
    artifact = tmp_path / "summary.json"
    artifact.write_text(json.dumps(summary), encoding="utf-8")
    assert json.loads(artifact.read_text())["totals"]["completed"] == 1
    svg = bar_chart({"C1": 1.0}, title="Fault detection", max_value=1.0)
    assert svg.startswith("<svg")
    assert "C1" in svg


def test_cli_check_and_conditions(capsys):
    assert main(["check"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["operation_nodes"] == 15
    assert main(["conditions"]) == 0
    listing = capsys.readouterr().out
    assert "C1_schema" in listing
    assert "C8_status_oracle" in listing
