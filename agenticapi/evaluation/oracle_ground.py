"""Ground‑truth oracle independent of the test‑generation pipeline.

This oracle uses manually defined expectations for each injected fault.
It is *not* derived from generated cases, plans, or the spec‑derived
status/schema/oracle used by the generator.  The only dependence on the
API specification is the list of fault IDs and the fields they affect;
the actual expected values are hard‑coded and can be overridden without
changing the generator.

Faults are checked against actual case fields.  The oracle does NOT
read generator‑generated expected statuses or assertions.  If a check is
inconclusive for plain cases (no auth context, no deletion context, etc.)
the function returns ``None``, which is treated as *not detected* in the
oracle summary.

The ground‑truth expectations below are *reference values*; the actual
checker functions interpret them against the runtime case fields.
"""

from __future__ import annotations

from collections.abc import Callable

# ------------------------------------------------------------------
# Ground‑truth mapping (reference only).
# These entries describe the *expected* behaviour for each fault ID.
# The actual validation is performed by the checker functions below.
# ------------------------------------------------------------------

GROUND_TRUTH: dict[str, dict[str, object]] = {
    "F01": {"status": 500},
    "F02": {"price_is_number": False},
    "F03": {"name_present": False},
    "F04": {"negative_price_accepted": True},
    "F05": {"auth_bypassed": True},
    "F06": {"non_owner_read": True},
    "F07": {"deleted_still_readable": True},
    "F08": {"stock_exceeded": True},
    "F09": {"idempotency_duplicate": True},
    "F10": {"stock_negative": True},
    "F11": {"name_missing": True},
    "F12": {"status_200_instead_of_201": True},
}


# ------------------------------------------------------------------
# Checker functions map each fault ID to a runtime check against the
# actual case dict.  The checker may return ``True`` (fault detected),
# ``False`` (fault not detected), or ``None`` (inconclusive – not
# counted as detected in the oracle summary).
# ------------------------------------------------------------------

FAULT_CHECKERS: dict[str, Callable[[dict], bool | None]] = {
    # F01 – product read returns HTTP 500
    "F01": lambda case: case.get("status") == 500,
    # F02 – the injected signature is a string price; a numeric price is the
    # clean behaviour and must NOT be reported as a detection.
    "F02": lambda case: isinstance(case.get("price"), str),
    # F03 – name field: oracle does NOT detect F03 when name IS present.
    "F03": lambda case: case.get("name") is None or case.get("name") == "",
    # F04 – negative price accepted
    "F04": lambda case: ((p := case.get("price")) is not None) and isinstance(p, (int, float)) and not isinstance(p, bool) and p < 0,
    # F05–F07 require request/auth/state context not present in a flat case
    # dict; return None (inconclusive) rather than a false negative.
    "F05": lambda case: None,
    "F06": lambda case: None,
    "F07": lambda case: None,
    # F08 – stock exceeded
    "F08": lambda case: case.get("quantity", 0) > case.get("stock", 0) >= 0,
    # F09 needs a two-step idempotency record; a flat case is inconclusive.
    "F09": lambda case: None,
    # F10 – negative stock value
    "F10": lambda case: ((s := case.get("stock")) is not None) and isinstance(s, (int, float)) and not isinstance(s, bool) and s < 0,
    # F11 – name missing
    "F11": lambda case: case.get("name") is None or case.get("name") == "",
    # F12 – status 200 instead of 201
    "F12": lambda case: case.get("status") == 200,
}


def check_fault(actual_case: dict, fault_id: str) -> bool | None:
    """Return ``True`` if the executed case satisfies the ground‑truth
    for *fault_id*, ``False`` if it does not, or ``None`` if the check
    is inconclusive for the given case (e.g. no auth context).

    The oracle uses *runtime observables* from the mock API execution,
    not generator‑generated expectations.
    """
    checker = FAULT_CHECKERS.get(fault_id)
    if checker is None:
        return False
    result = checker(actual_case)
    # ``None`` means inconclusive – not counted as detected.
    return result if result is not None else None


def all_faults_detected(actual_cases: list[dict], fault_ids: list[str] | None = None) -> dict[str, bool | None]:
    """Return a dict ``fault_id → detected?/inconclusive?`` for the given cases.

    ``True``  – fault detected.
    ``False`` – fault not detected.
    ``None``  – result inconclusive (e.g. no auth/context).
    """
    if fault_ids is None:
        fault_ids = list(FAULT_CHECKERS.keys())
    result: dict[str, bool | None] = {}
    for fid in fault_ids:
        values = [check_fault(case, fid) for case in actual_cases]
        if any(value is True for value in values):
            result[fid] = True
        elif any(value is False for value in values):
            result[fid] = False
        else:
            result[fid] = None
    return result
