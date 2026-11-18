"""Independent, differential ground truth for injected-fault experiments.

The predicates in this module inspect the case stimulus and the raw HTTP
response.  They do not read generated assertions, expected statuses, or the
spec-derived oracle.  A fault is considered observed only when the injected
signature is present in the fault execution and absent from the paired clean
execution.
"""

from __future__ import annotations

from typing import Any, cast

Case = dict[str, Any]
Record = dict[str, Any]


def _parts(path: str) -> list[str]:
    return str(path).split("?", 1)[0].strip("/").split("/")


def _is_template(segment: str) -> bool:
    return segment.startswith("{") and segment.endswith("}")


def _path_matches(actual: str, expected: str) -> bool:
    actual_parts = _parts(actual)
    expected_parts = _parts(expected)
    if len(actual_parts) != len(expected_parts):
        return False
    for left, right in zip(actual_parts, expected_parts, strict=False):
        if left == right or _is_template(left) or _is_template(right):
            continue
        return False
    return True


def _method(step: dict[str, Any]) -> str:
    return str(step.get("method", "")).upper()


def _body(step: dict[str, Any]) -> dict[str, Any]:
    body = step.get("body")
    return body if isinstance(body, dict) else {}


def _status(step: dict[str, Any]) -> int | None:
    value = step.get("status_code")
    return value if isinstance(value, int) else None


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _pairs(case: Case, record: Record) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    case_steps = cast(
        list[Any], case.get("steps") if isinstance(case.get("steps"), list) else []
    )
    record_steps = cast(
        list[Any], record.get("steps") if isinstance(record.get("steps"), list) else []
    )
    return [
        (case_step, record_step)
        for case_step, record_step in zip(case_steps, record_steps, strict=False)
        if isinstance(case_step, dict) and isinstance(record_step, dict)
    ]


def _idempotency_key(step: dict[str, Any]) -> str:
    headers = step.get("headers")
    if not isinstance(headers, dict):
        return ""
    for key, value in headers.items():
        if str(key).lower() == "idempotency-key":
            return str(value)
    return ""


def _idempotent_pairs(case: Case) -> list[dict[str, Any]]:
    steps = cast(
        list[Any], case.get("steps") if isinstance(case.get("steps"), list) else []
    )
    return [
        step
        for step in steps
        if isinstance(step, dict)
        and _method(step) == "POST"
        and _path_matches(str(step.get("path", "")), "/orders")
        and _idempotency_key(step)
    ]


def case_exercises_fault(case: Case, fault_id: str) -> bool:
    """Return whether the case stimulus can expose ``fault_id``."""
    steps = cast(
        list[Any], case.get("steps") if isinstance(case.get("steps"), list) else []
    )
    steps = [step for step in steps if isinstance(step, dict)]
    if fault_id in {"F01", "F02", "F03", "F10"}:
        return any(
            _method(step) == "GET"
            and _path_matches(str(step.get("path", "")), "/products/p1")
            for step in steps
        )
    if fault_id == "F04":
        return any(
            _method(step) == "POST"
            and _path_matches(str(step.get("path", "")), "/products")
            and (price := _body(step).get("price")) is not None
            and _is_number(price)
            and price < 0
            for step in steps
        )
    if fault_id == "F05":
        return any(
            _method(step) == "GET"
            and _path_matches(str(step.get("path", "")), "/orders")
            and not step.get("auth")
            for step in steps
        )
    if fault_id == "F06":
        return any(
            _method(step) == "GET"
            and _path_matches(str(step.get("path", "")), "/orders/o1")
            and bool(step.get("auth"))
            for step in steps
        )
    if fault_id == "F07":
        deleted = {
            str(step.get("path", ""))
            for step in steps
            if _method(step) == "DELETE"
            and _path_matches(str(step.get("path", "")), "/products/{product_id}")
        }
        return bool(deleted) and any(
            _method(step) == "GET"
            and _path_matches(str(step.get("path", "")), "/products/{product_id}")
            for step in steps
        )
    if fault_id == "F08":
        return any(
            _method(step) == "POST"
            and _path_matches(str(step.get("path", "")), "/orders")
            and _is_number(_body(step).get("quantity"))
            and _body(step)["quantity"] > 5
            for step in steps
        )
    if fault_id == "F09":
        pairs = _idempotent_pairs(case)
        keys = [_idempotency_key(step) for step in pairs]
        return len(pairs) >= 2 and len(set(keys)) == 1
    if fault_id == "F11":
        return any(
            _method(step) == "POST"
            and _path_matches(str(step.get("path", "")), "/products")
            and not _body(step).get("name")
            for step in steps
        )
    if fault_id == "F12":
        return any(
            _method(step) == "POST"
            and _path_matches(str(step.get("path", "")), "/products")
            and bool(_body(step).get("name"))
            and _is_number(_body(step).get("price"))
            and _body(step)["price"] >= 0
            for step in steps
        )
    return False


def observed_fault_signature(case: Case, record: Record, fault_id: str) -> bool | None:
    """Return whether the raw response contains the injected signature.

    ``True`` means the injected fault is visible, ``False`` means the relevant
    request was executed without the signature, and ``None`` means the case did
    not exercise the fault or the record is incomplete.
    """
    pairs = _pairs(case, record)
    if fault_id in {"F01", "F02", "F03", "F10"}:
        relevant = [
            response
            for stimulus, response in pairs
            if _method(stimulus) == "GET"
            and _path_matches(str(stimulus.get("path", "")), "/products/p1")
        ]
        if not relevant:
            return None
        if fault_id == "F01":
            return any(_status(response) == 500 for response in relevant)
        bodies = [_body(response) for response in relevant]
        if fault_id == "F02":
            return any(isinstance(body.get("price"), str) for body in bodies)
        if fault_id == "F03":
            return any(not body.get("name") for body in bodies)
        return any(_is_number(body.get("stock")) and body["stock"] < 0 for body in bodies)
    if fault_id == "F04":
        relevant = [
            response
            for stimulus, response in pairs
            if _method(stimulus) == "POST"
            and _path_matches(str(stimulus.get("path", "")), "/products")
            and _is_number(_body(stimulus).get("price"))
            and _body(stimulus)["price"] < 0
        ]
        if not relevant:
            return None
        return any(_status(response) == 201 for response in relevant)
    if fault_id == "F05":
        relevant = [
            response
            for stimulus, response in pairs
            if _method(stimulus) == "GET"
            and _path_matches(str(stimulus.get("path", "")), "/orders")
            and not stimulus.get("auth")
        ]
        if not relevant:
            return None
        return any(_status(response) == 200 for response in relevant)
    if fault_id == "F06":
        relevant = [
            response
            for stimulus, response in pairs
            if _method(stimulus) == "GET"
            and _path_matches(str(stimulus.get("path", "")), "/orders/o1")
            and bool(stimulus.get("auth"))
        ]
        if not relevant:
            return None
        return any(_status(response) == 200 for response in relevant)
    if fault_id == "F07":
        deleted: set[str] = set()
        saw_relevant = False
        for stimulus, response in pairs:
            path = str(stimulus.get("path", ""))
            if _method(stimulus) == "DELETE" and _path_matches(
                path, "/products/{product_id}"
            ):
                deleted.add(path)
                continue
            if (
                deleted
                and _method(stimulus) == "GET"
                and _path_matches(path, "/products/{product_id}")
            ):
                saw_relevant = True
                if _status(response) == 200:
                    return True
        return False if saw_relevant else None
    if fault_id == "F08":
        relevant = [
            response
            for stimulus, response in pairs
            if _method(stimulus) == "POST"
            and _path_matches(str(stimulus.get("path", "")), "/orders")
            and _is_number(_body(stimulus).get("quantity"))
            and _body(stimulus)["quantity"] > 5
        ]
        if not relevant:
            return None
        return any(_status(response) == 201 for response in relevant)
    if fault_id == "F09":
        relevant = [
            response
            for stimulus, response in pairs
            if _method(stimulus) == "POST"
            and _path_matches(str(stimulus.get("path", "")), "/orders")
            and _idempotency_key(stimulus)
        ]
        if len(relevant) < 2:
            return None
        ids = [
            _body(response).get("id")
            for response in relevant
            if _status(response) == 201
        ]
        return len(ids) >= 2 and len(set(ids)) > 1
    if fault_id == "F11":
        relevant = [
            response
            for stimulus, response in pairs
            if _method(stimulus) == "POST"
            and _path_matches(str(stimulus.get("path", "")), "/products")
            and not _body(stimulus).get("name")
        ]
        if not relevant:
            return None
        return any(_status(response) == 201 for response in relevant)
    if fault_id == "F12":
        relevant = [
            response
            for stimulus, response in pairs
            if _method(stimulus) == "POST"
            and _path_matches(str(stimulus.get("path", "")), "/products")
            and bool(_body(stimulus).get("name"))
            and _is_number(_body(stimulus).get("price"))
            and _body(stimulus)["price"] >= 0
        ]
        if not relevant:
            return None
        return any(_status(response) == 200 for response in relevant)
    return None


def differential_ground_truth(
    case: Case,
    clean_record: Record | None,
    fault_record: Record,
    fault_id: str,
) -> bool | None:
    """Return True when the fault signature appears only under injection."""
    fault_signal = observed_fault_signature(case, fault_record, fault_id)
    if fault_signal is None:
        return None
    if not fault_signal:
        return False
    clean_signal = (
        observed_fault_signature(case, clean_record, fault_id)
        if clean_record is not None
        else False
    )
    return True if clean_signal is not True else None
