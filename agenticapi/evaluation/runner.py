"""Experiment runner: conditions, seeds, aggregation, and artifacts."""

from __future__ import annotations

import csv
import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agenticapi.agents.orchestrator import Orchestrator, new_run_dir
from agenticapi.config import Settings
from agenticapi.evaluation.charts import bar_chart, write_chart
from agenticapi.evaluation.conditions import DEFAULT_CONDITIONS, condition_by_id
from agenticapi.evaluation.faults import all_faults
from agenticapi.evaluation.manifest import build_run_manifest, write_sha256sums
from agenticapi.llm.provider import LLMProvider
from agenticapi.mock_api.server import MockAPIServer
from agenticapi.models import ConditionResult, ConditionStatus, ExperimentConfig, write_json
from agenticapi.spec.graph import build_dependency_graph, graph_metrics
from agenticapi.spec.loader import load_spec


def load_experiment_config(path: str | Path | None = None) -> ExperimentConfig:
    if path is None:
        return ExperimentConfig()
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    allowed = {field for field in ExperimentConfig.__dataclass_fields__}
    filtered = {key: value for key, value in data.items() if key in allowed}
    return ExperimentConfig(**filtered)


def run_experiment(
    settings: Settings,
    config: ExperimentConfig,
    *,
    condition_ids: list[str] | None = None,
    seeds: list[int] | None = None,
    run_faults: bool = True,
    label: str = "",
    provider: LLMProvider | None = None,
) -> dict[str, Any]:
    spec = load_spec(config.spec_path)
    graph = build_dependency_graph(spec)
    selected = condition_ids or config.conditions or DEFAULT_CONDITIONS
    selected_seeds = seeds or config.seeds or [1]
    run_dir = new_run_dir(settings, label)
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest = build_run_manifest(settings, spec, config, selected, selected_seeds)
    write_json(
        run_dir / "run.json",
        {
            "config": config,
            "spec": spec.source_path,
            "spec_title": spec.title,
            "spec_version": spec.openapi_version,
            "conditions": selected,
            "seeds": selected_seeds,
            "graph": graph_metrics(spec, graph),
            "faults": [fault.to_dict() for fault in all_faults()],
            "manifest": manifest,
        },
    )
    results: list[ConditionResult] = []
    with MockAPIServer() as server:
        orchestrator = Orchestrator(
            settings,
            spec,
            graph,
            server,
            run_dir,
            provider=provider,
        )
        for condition_id in selected:
            condition = condition_by_id(condition_id)
            if not run_faults:
                condition = replace(condition, use_faults=False)
            for seed in selected_seeds:
                results.append(orchestrator.run_condition(condition, seed))
    summary = aggregate(results, selected, selected_seeds)
    summary["run_dir"] = str(run_dir)
    summary["manifest"] = manifest
    summary["spec"] = {
        "path": spec.source_path,
        "title": spec.title,
        "version": spec.openapi_version,
        "metrics": graph_metrics(spec, graph),
    }
    write_json(run_dir / "summary.json", summary)
    _write_csv(run_dir / "results.csv", results)
    _write_charts(run_dir / "charts", summary["conditions"])
    write_sha256sums(run_dir)
    return summary


def aggregate(
    results: list[ConditionResult],
    condition_ids: list[str],
    seeds: list[int],
) -> dict[str, Any]:
    grouped: dict[str, list[ConditionResult]] = {condition_id: [] for condition_id in condition_ids}
    for result in results:
        grouped.setdefault(result.condition, []).append(result)
    conditions: dict[str, Any] = {}
    for condition_id, runs in grouped.items():
        completed = [run for run in runs if run.status is ConditionStatus.COMPLETED]
        metrics = [run.metrics for run in completed]
        conditions[condition_id] = {
            "statuses": [run.status.value for run in runs],
            "runs": len(runs),
            "completed": len(completed),
            "cases_generated_mean": _mean([run.cases_generated for run in completed]),
            "cases_valid_mean": _mean([run.cases_valid for run in completed]),
            "cases_executed_mean": _mean([run.cases_executed for run in completed]),
            "pass_rate_mean": _mean([float(item.get("pass_rate", 0.0)) for item in metrics]),
            "valid_test_rate_mean": _mean(
                [float(item.get("valid_test_rate", 0.0)) for item in metrics]
            ),
            "clean_false_alarm_rate_mean": _mean(
                [float(item.get("clean_false_alarm_rate", 0.0)) for item in metrics]
            ),
            "fault_detection_rate_mean": _mean(
                [float(item.get("fault_detection_rate", 0.0)) for item in metrics]
            ),
            "fault_detection_rate_with_opportunity_mean": _mean(
                [
                    float(item.get("fault_detection_rate_with_opportunity", 0.0))
                    for item in metrics
                ]
            ),
            "faults_detected_mean": _mean(
                [float(item.get("faults_detected", 0)) for item in metrics]
            ),
            "faults_no_opportunity_mean": _mean(
                [float(item.get("faults_no_opportunity", 0)) for item in metrics]
            ),
            "precision_mean": _mean(
                [
                    float(item.get("fault_level_matrix", {}).get("precision", 0.0))
                    for item in metrics
                ]
            ),
            "recall_mean": _mean(
                [
                    float(item.get("fault_level_matrix", {}).get("recall", 0.0))
                    for item in metrics
                ]
            ),
            "f1_mean": _mean(
                [
                    float(item.get("fault_level_matrix", {}).get("f1", 0.0))
                    for item in metrics
                ]
            ),
            "accuracy_mean": _mean(
                [
                    float(item.get("fault_level_matrix", {}).get("accuracy", 0.0))
                    for item in metrics
                ]
            ),
            "repair_attempted_mean": _mean(
                [float(item.get("repair", {}).get("attempted", 0)) for item in metrics]
            ),
            "repair_llm_repaired_mean": _mean(
                [
                    float(item.get("repair", {}).get("llm_repaired", 0))
                    for item in metrics
                ]
            ),
            "coverage_operation_mean": _mean(
                [
                    float(item.get("coverage", {}).get("operation_coverage", 0.0))
                    for item in metrics
                ]
            ),
            "coverage_technique_mean": _mean(
                [
                    float(item.get("coverage", {}).get("technique_coverage", 0.0))
                    for item in metrics
                ]
            ),
            "llm_calls_mean": _mean([run.llm_calls for run in completed]),
            "prompt_tokens_mean": _mean([run.prompt_tokens for run in completed]),
            "completion_tokens_mean": _mean([run.completion_tokens for run in completed]),
            "cost_usd_mean": _cost_mean([run.cost_usd for run in completed]),
            "duration_seconds_mean": _mean([run.duration_seconds for run in completed]),
            "errors": sorted({error for run in runs for error in run.errors}),
            "is_llm": any(run.is_llm for run in runs),
            "seeds": seeds,
        }
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "conditions": conditions,
        "totals": {
            "runs": len(results),
            "completed": sum(1 for result in results if result.status is ConditionStatus.COMPLETED),
            "blocked": sum(1 for result in results if result.status is ConditionStatus.BLOCKED),
            "failed": sum(1 for result in results if result.status is ConditionStatus.FAILED),
        },
    }


def _mean(values: list[float | int]) -> float:
    return round(sum(float(value) for value in values) / len(values), 4) if values else 0.0


def _cost_mean(values: list[float | None]) -> float | None:
    known = [value for value in values if value is not None]
    if not known:
        return None
    return round(sum(known) / len(known), 6)


def _write_csv(path: Path, results: list[ConditionResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "condition",
        "seed",
        "status",
        "provider",
        "is_llm",
        "cases_generated",
        "cases_valid",
        "cases_executed",
        "pass_rate",
        "valid_test_rate",
        "clean_false_alarm_rate",
        "faults_detected",
        "faults_no_opportunity",
        "fault_detection_rate",
        "fault_detection_rate_with_opportunity",
        "precision",
        "recall",
        "f1",
        "accuracy",
        "repair_attempted",
        "repair_llm_repaired",
        "coverage_operation",
        "coverage_technique",
        "llm_calls",
        "prompt_tokens",
        "completion_tokens",
        "cost_usd",
        "duration_seconds",
        "errors",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for result in results:
            writer.writerow(
                {
                    "condition": result.condition,
                    "seed": result.seed,
                    "status": result.status.value,
                    "provider": result.provider,
                    "is_llm": result.is_llm,
                    "cases_generated": result.cases_generated,
                    "cases_valid": result.cases_valid,
                    "cases_executed": result.cases_executed,
                    "pass_rate": result.metrics.get("pass_rate", ""),
                    "valid_test_rate": result.metrics.get("valid_test_rate", ""),
                    "clean_false_alarm_rate": result.metrics.get(
                        "clean_false_alarm_rate", ""
                    ),
                    "faults_detected": result.metrics.get("faults_detected", ""),
                    "faults_no_opportunity": result.metrics.get(
                        "faults_no_opportunity", ""
                    ),
                    "fault_detection_rate": result.metrics.get("fault_detection_rate", ""),
                    "fault_detection_rate_with_opportunity": result.metrics.get(
                        "fault_detection_rate_with_opportunity", ""
                    ),
                    "precision": result.metrics.get("fault_level_matrix", {}).get(
                        "precision", ""
                    ),
                    "recall": result.metrics.get("fault_level_matrix", {}).get(
                        "recall", ""
                    ),
                    "f1": result.metrics.get("fault_level_matrix", {}).get("f1", ""),
                    "accuracy": result.metrics.get("fault_level_matrix", {}).get(
                        "accuracy", ""
                    ),
                    "repair_attempted": result.metrics.get("repair", {}).get(
                        "attempted", ""
                    ),
                    "repair_llm_repaired": result.metrics.get("repair", {}).get(
                        "llm_repaired", ""
                    ),
                    "coverage_operation": result.metrics.get("coverage", {}).get(
                        "operation_coverage", ""
                    ),
                    "coverage_technique": result.metrics.get("coverage", {}).get(
                        "technique_coverage", ""
                    ),
                    "llm_calls": result.llm_calls,
                    "prompt_tokens": result.prompt_tokens,
                    "completion_tokens": result.completion_tokens,
                    "cost_usd": "" if result.cost_usd is None else result.cost_usd,
                    "duration_seconds": round(result.duration_seconds, 4),
                    "errors": " | ".join(result.errors),
                }
            )


def _write_charts(directory: Path, conditions: dict[str, Any]) -> None:
    detection = {
        key: float(value.get("fault_detection_rate_mean", 0.0))
        for key, value in conditions.items()
    }
    pass_rate = {
        key: float(value.get("pass_rate_mean", 0.0))
        for key, value in conditions.items()
    }
    write_chart(
        directory / "fault_detection.svg",
        bar_chart(detection, title="Fault detection rate by condition", max_value=1.0),
    )
    write_chart(
        directory / "pass_rate.svg",
        bar_chart(pass_rate, title="Clean-run pass rate by condition", max_value=1.0),
    )
