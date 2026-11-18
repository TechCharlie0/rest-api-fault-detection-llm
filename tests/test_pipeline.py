"""Integration tests for conditions and the orchestrated pipeline."""

import socket

from agenticapi.evaluation.conditions import CONDITIONS
from agenticapi.evaluation.oracle_ground import check_fault


def get_free_port():
    """Get a free TCP port."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_ground_truth_oracle():
    """Verify that the ground‑truth oracle correctly detects (or misses) faults
    based on hard‑coded expectations, independent of generated cases."""
    # F01 – status 500
    assert check_fault({"status": 500, "price": 99.99, "name": "Widget"}, "F01") is True

    # F02 – a string price is the injected signature
    assert check_fault({"status": 200, "price": "99.99", "name": "Widget"}, "F02") is True
    assert check_fault({"status": 200, "price": 99.99, "name": "Widget"}, "F02") is False

    # F03 – name omitted should NOT be detected (expect name_present False)
    assert not check_fault({"status": 200, "price": 99.99, "name": "Widget"}, "F03")

    # F04 – negative price accepted
    assert check_fault({"status": 200, "price": -5, "name": "Widget"}, "F04") is True

    # F12 – status 200 instead of 201
    assert check_fault({"status": 200, "price": 99.99, "name": "Widget"}, "F12") is True

    # Context-dependent faults are inconclusive for a flat case dict
    assert check_fault({"status": 200, "price": 99.99, "name": "Widget"}, "F05") is None


def test_c5_no_validator_spec():
    """C5_no_validator: use_validator=False means validator gate is skipped.

    This is verified from the condition specification alone:
    - use_validator=False
    - C5 has use_repair=True (repair still runs independently)
    - C5 has use_execution_feedback=True (flag should be True)
    """
    c5 = CONDITIONS["C5_no_validator"]
    assert c5.use_validator is False, "C5 should have use_validator=False"
    assert c5.use_repair is True, "C5 should have use_repair=True"
    assert c5.use_execution_feedback is True, "C5 should have use_execution_feedback=True"


def test_c6_no_execution_feedback_spec():
    """C6_no_execution_feedback: use_execution_feedback=False.

    The flag should be False regardless of runtime.
    """
    c6 = CONDITIONS["C6_no_execution_feedback"]
    assert c6.use_execution_feedback is False, "C6 should have use_execution_feedback=False"


def test_c7_no_repair_spec():
    """C7_no_repair: use_execution_feedback=True and use_repair=False.

    The flag should be True and repair should be disabled.
    """
    c7 = CONDITIONS["C7_no_repair"]
    assert c7.use_execution_feedback is True, "C7 should have use_execution_feedback=True"
    assert c7.use_repair is False, "C7 should have use_repair=False"


def test_c6_c7_difference():
    """C6 and C7 must have opposite execution_feedback_applied flags.

    This is the key differentiation: C6 disables execution feedback,
    C7 enables it while disabling repair.
    """
    c6 = CONDITIONS["C6_no_execution_feedback"]
    c7 = CONDITIONS["C7_no_repair"]
    assert c6.use_execution_feedback is False
    assert c7.use_execution_feedback is True
    assert c6.use_repair is True, "C6 should still have repair enabled"
    assert c7.use_repair is False, "C7 should disable repair"