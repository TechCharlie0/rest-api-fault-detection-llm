"""Differential metrics for clean/fault paired experiments.

A fault counts as detected only when a case that exercises the fault passes in
the clean run and fails under the injected fault.  ``ERROR`` and
``INVALID_TEST`` outcomes are reported separately and are never detections.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from agenticapi.evaluation.faults import all_faults
from agenticapi.evaluation.ground_truth import (
    case_exercises_fault,
    differential_ground_truth,
)
from agenticapi.models import Fault, FaultCategory, OracleResult, Outcome, Technique, TestCase


def summarize(
    oracle_results: list[OracleResult],
    fault_results: dict[str, list[OracleResult]],
    *,
    eligible_fault_ids: list[str] | None = None,
    cases: list[TestCase] | None = None,
    fault_catalogue: list[Fault] | None = None,
    clean_records: dict[str, dict[str, Any]] | None = None,
    fault_records: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    catalogue = fault_catalogue or all_faults()
    catalogue_by_id = {fault.fault_id: fault for fault in catalogue}
    eligible = [
        fault_id
        for fault_id in (eligible_fault_ids or [fault.fault_id for fault in catalogue])
        if fault_id in catalogue_by_id
    ]
    clean_by_case = {result.case_id: result.outcome for result in oracle_results}
    case_by_id = {case.case_id: case for case in cases or []}
    clean_record_by_id = clean_records or {}
    raw_fault_by_case: dict[str, dict[str, dict[str, Any]]] = {}
    for fault_id, items in (fault_records or {}).items():
        raw_fault_by_case[fault_id] = {
            str(item["case"]["case_id"]): item["record"]
            for item in items
            if isinstance(item, dict)
            and isinstance(item.get("case"), dict)
            and isinstance(item.get("record"), dict)
            and isinstance(item["case"].get("case_id"), str)
        }

    outcomes = Counter(result.outcome.value for result in oracle_results)
    failures = Counter(
        result.failure_kind for result in oracle_results if result.outcome is not Outcome.PASS
    )

    fault_details: dict[str, dict[str, Any]] = {}
    detected_faults: list[str] = []
    missed_faults: list[str] = []
    no_opportunity_faults: list[str] = []
    ground_truth_true: list[str] = []
    oracle_gaps: list[str] = []
    spurious_detections: list[str] = []
    agreement_faults: list[str] = []
    detected_case_pairs = 0
    missed_case_pairs = 0
    clean_failure_pairs = 0
    error_pairs = 0
    invalid_pairs = 0

    for fault_id in eligible:
        results = fault_results.get(fault_id, [])
        if cases is None:
            opportunity_ids = {result.case_id for result in results}
        else:
            opportunity_ids = {
                case.case_id
                for case in cases
                if case_exercises_fault(case.to_dict(), fault_id)
            }
        clean_pass_ids = {
            case_id
            for case_id in opportunity_ids
            if clean_by_case.get(case_id) is Outcome.PASS
        }
        detected_ids = []
        for result in results:
            if (
                result.case_id in clean_pass_ids
                and result.outcome is Outcome.FAIL
            ):
                detected_ids.append(result.case_id)
        clean_fail_ids = sorted(
            case_id
            for case_id in opportunity_ids
            if clean_by_case.get(case_id) is Outcome.FAIL
        )
        error_ids = sorted(
            result.case_id for result in results if result.outcome is Outcome.ERROR
        )
        invalid_ids = sorted(
            result.case_id for result in results if result.outcome is Outcome.INVALID_TEST
        )
        detected = bool(detected_ids)
        if detected:
            detected_faults.append(fault_id)
        else:
            missed_faults.append(fault_id)
        if not opportunity_ids:
            no_opportunity_faults.append(fault_id)

        detected_case_pairs += len(detected_ids)
        missed_case_pairs += max(0, len(clean_pass_ids) - len(detected_ids))
        clean_failure_pairs += len(clean_fail_ids)
        error_pairs += len(error_ids)
        invalid_pairs += len(invalid_ids)

        gt_value: bool | None = None
        if fault_records is not None:
            values: list[bool] = []
            for result in results:
                raw_fault = raw_fault_by_case.get(fault_id, {}).get(result.case_id)
                if raw_fault is None:
                    continue
                case = case_by_id.get(result.case_id)
                if case is None:
                    continue
                case_dict = case.to_dict()
                value = differential_ground_truth(
                    case_dict,
                    clean_record_by_id.get(result.case_id),
                    raw_fault,
                    fault_id,
                )
                if value is not None:
                    values.append(value)
            if values:
                gt_value = any(values)
                if gt_value:
                    ground_truth_true.append(fault_id)
                if gt_value and not detected:
                    oracle_gaps.append(fault_id)
                if detected and not gt_value:
                    spurious_detections.append(fault_id)
                if gt_value == detected:
                    agreement_faults.append(fault_id)

        fault_details[fault_id] = {
            "eligible": True,
            "cases_run": len(results),
            "opportunity_cases": len(opportunity_ids),
            "clean_pass_cases": len(clean_pass_ids),
            "detected": detected,
            "missed": not detected,
            "no_opportunity": not opportunity_ids,
            "detected_case_ids": sorted(detected_ids),
            "clean_fail_case_ids": clean_fail_ids,
            "error_case_ids": error_ids,
            "invalid_case_ids": invalid_ids,
            "ground_truth_observed": gt_value,
            "oracle_gap": (True if gt_value and not detected else False)
            if gt_value is not None
            else None,
            "spurious_detection": (True if detected and not gt_value else False)
            if gt_value is not None
            else None,
        }

    opportunity_count = len(eligible) - len(no_opportunity_faults)
    tp = len(detected_faults)
    fn = max(0, opportunity_count - tp)
    fp = sum(
        1
        for fault_id in eligible
        if fault_details[fault_id]["clean_fail_case_ids"]
    )
    tn = max(0, opportunity_count - fp)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    matrix_total = tp + tn + fp + fn
    accuracy = (tp + tn) / matrix_total if matrix_total else 0.0

    by_category: dict[str, dict[str, int]] = {}
    for category in FaultCategory:
        relevant = [
            fault_id
            for fault_id in eligible
            if catalogue_by_id[fault_id].category == category
        ]
        if not relevant:
            continue
        by_category[category.value] = {
            "detected": sum(1 for fault_id in relevant if fault_id in detected_faults),
            "total": len(relevant),
        }

    total = len(oracle_results)
    return {
        "clean_cases": total,
        "pass": outcomes.get("PASS", 0),
        "fail": outcomes.get("FAIL", 0),
        "error": outcomes.get("ERROR", 0),
        "invalid_test": outcomes.get("INVALID_TEST", 0),
        "inconclusive": outcomes.get("INCONCLUSIVE", 0),
        "valid_test_rate": (outcomes.get("PASS", 0) / total) if total else 0.0,
        "clean_false_alarm_rate": (outcomes.get("FAIL", 0) / total) if total else 0.0,
        "error_rate": (outcomes.get("ERROR", 0) / total) if total else 0.0,
        "invalid_test_rate": (outcomes.get("INVALID_TEST", 0) / total) if total else 0.0,
        "pass_rate": (outcomes.get("PASS", 0) / total) if total else 0.0,
        "failure_kinds": dict(sorted(failures.items())),
        "faults_total": len(eligible),
        "faults_detected": tp,
        "faults_missed": len(missed_faults),
        "faults_no_opportunity": len(no_opportunity_faults),
        "fault_opportunity_rate": (opportunity_count / len(eligible)) if eligible else 0.0,
        "fault_detection_rate": (tp / len(eligible)) if eligible else 0.0,
        "fault_detection_rate_with_opportunity": (tp / opportunity_count)
        if opportunity_count
        else 0.0,
        "detected_faults": detected_faults,
        "missed_faults": missed_faults,
        "no_opportunity_faults": no_opportunity_faults,
        "fault_details": fault_details,
        "faults_by_category": by_category,
        "fault_catalogue_categories": dict(
            sorted(Counter(fault.category.value for fault in catalogue).items())
        ),
        "fault_level_matrix": {
            "tp": tp,
            "fp": fp,
            "tn": tn,
            "fn": fn,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "accuracy": accuracy,
            "opportunity_faults": opportunity_count,
        },
        "case_pairs": {
            "detected": detected_case_pairs,
            "missed": missed_case_pairs,
            "clean_failures": clean_failure_pairs,
            "errors": error_pairs,
            "invalid": invalid_pairs,
        },
        "ground_truth": {
            "observed_faults": ground_truth_true,
            "oracle_gaps": oracle_gaps,
            "spurious_detections": spurious_detections,
            "agreements": agreement_faults,
        },
    }


def coverage_metrics(
    cases: list[TestCase],
    *,
    operations_total: int,
    techniques_total: int = len(Technique),
) -> dict[str, Any]:
    operations = {case.operation_id for case in cases}
    techniques = Counter(case.technique.value for case in cases)
    return {
        "cases": len(cases),
        "operations_covered": len(operations),
        "operations_total": operations_total,
        "operation_coverage": (len(operations) / operations_total)
        if operations_total
        else 0.0,
        "techniques_covered": len(techniques),
        "techniques_total": techniques_total,
        "technique_coverage": (len(techniques) / techniques_total)
        if techniques_total
        else 0.0,
        "cases_by_technique": dict(sorted(techniques.items())),
        "operations": sorted(operations),
    }
