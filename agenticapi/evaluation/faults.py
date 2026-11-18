"""Deterministic fault catalogue with ground-truth metadata.

Each fault is observable through at least one valid test oracle.  The local mock
server implements the corresponding behaviour; this module is the single source
of truth for IDs, categories, descriptions, and expected observable behaviour.
"""

from __future__ import annotations

from agenticapi.models import Fault, FaultCategory, Operation

FAULTS: dict[str, Fault] = {
    "F01": Fault(
        fault_id="F01",
        category=FaultCategory.STATUS,
        description="GET /products/p1 returns HTTP 500 instead of 200.",
        operation_id="get_product",
        method="GET",
        path="/products/p1",
        location="response.status",
        expected_behavior="A valid product request must return HTTP 200.",
        activation={"resource_id": "p1", "injected_status": 500},
        ground_truth={"detectable_by": ["status assertion"]},
    ),
    "F02": Fault(
        fault_id="F02",
        category=FaultCategory.SCHEMA,
        description="GET /products/p1 returns price as a string instead of a number.",
        operation_id="get_product",
        method="GET",
        path="/products/p1",
        location="response.body.price",
        expected_behavior="price must be a JSON number.",
        activation={"resource_id": "p1", "field": "price", "injected_type": "string"},
        ground_truth={"detectable_by": ["response schema validation"]},
    ),
    "F03": Fault(
        fault_id="F03",
        category=FaultCategory.SCHEMA,
        description="GET /products/p1 omits the required name field.",
        operation_id="get_product",
        method="GET",
        path="/products/p1",
        location="response.body.name",
        expected_behavior="name is required by the Product schema.",
        activation={"resource_id": "p1", "removed_field": "name"},
        ground_truth={"detectable_by": ["required-field validation"]},
    ),
    "F04": Fault(
        fault_id="F04",
        category=FaultCategory.BOUNDARY,
        description="POST /products accepts a negative price instead of rejecting it.",
        operation_id="create_product",
        method="POST",
        path="/products",
        location="request.body.price",
        expected_behavior="a negative price must return HTTP 400.",
        activation={"field": "price", "value": -1},
        ground_truth={"detectable_by": ["negative boundary test expectation"]},
    ),
    "F05": Fault(
        fault_id="F05",
        category=FaultCategory.AUTH,
        description="GET /orders allows an unauthenticated request.",
        operation_id="list_my_orders",
        method="GET",
        path="/orders",
        location="request.authorization",
        expected_behavior="missing credentials must return HTTP 401.",
        activation={"bypass": "missing_token"},
        ground_truth={"detectable_by": ["authentication test"]},
    ),
    "F06": Fault(
        fault_id="F06",
        category=FaultCategory.AUTHZ,
        description="GET /orders/o1 allows a non-owner to read another user's order.",
        operation_id="get_order",
        method="GET",
        path="/orders/o1",
        location="request.authorization",
        expected_behavior="a non-owner must receive HTTP 403.",
        activation={"resource_id": "o1", "cross_user": "alice"},
        ground_truth={"detectable_by": ["authorization test"]},
    ),
    "F07": Fault(
        fault_id="F07",
        category=FaultCategory.STATE,
        description="DELETE /products/{id} removes the product from the list but GET still returns it.",
        operation_id="delete_product",
        method="DELETE",
        path="/products/{product_id}",
        location="resource.state",
        expected_behavior="after a successful delete, GET must return HTTP 404.",
        activation={"state_inconsistency": "deleted_but_readable"},
        ground_truth={"detectable_by": ["stateful delete-then-read test"]},
    ),
    "F08": Fault(
        fault_id="F08",
        category=FaultCategory.BUSINESS_RULE,
        description="POST /orders accepts quantity greater than available stock.",
        operation_id="create_order",
        method="POST",
        path="/orders",
        location="request.body.quantity",
        expected_behavior="quantity greater than stock must return HTTP 400.",
        activation={"product_id": "p1", "quantity": 999},
        ground_truth={"detectable_by": ["business-rule test"]},
    ),
    "F09": Fault(
        fault_id="F09",
        category=FaultCategory.IDEMPOTENCY,
        description="POST /orders ignores Idempotency-Key and creates duplicate orders.",
        operation_id="create_order",
        method="POST",
        path="/orders",
        location="request.headers.Idempotency-Key",
        expected_behavior="the same Idempotency-Key must return the same order ID.",
        activation={"header": "Idempotency-Key", "duplicate": True},
        ground_truth={"detectable_by": ["idempotency state test"]},
    ),
    "F10": Fault(
        fault_id="F10",
        category=FaultCategory.BOUNDARY,
        description="GET /products/p1 returns a negative stock value.",
        operation_id="get_product",
        method="GET",
        path="/products/p1",
        location="response.body.stock",
        expected_behavior="stock must be an integer greater than or equal to zero.",
        activation={"resource_id": "p1", "stock": -1},
        ground_truth={"detectable_by": ["minimum constraint validation"]},
    ),
    "F11": Fault(
        fault_id="F11",
        category=FaultCategory.SCHEMA,
        description="POST /products accepts a product without a name.",
        operation_id="create_product",
        method="POST",
        path="/products",
        location="request.body.name",
        expected_behavior="missing required name must return HTTP 400.",
        activation={"removed_field": "name"},
        ground_truth={"detectable_by": ["missing-required-field test"]},
    ),
    "F12": Fault(
        fault_id="F12",
        category=FaultCategory.STATUS,
        description="POST /products returns HTTP 200 instead of the documented HTTP 201.",
        operation_id="create_product",
        method="POST",
        path="/products",
        location="response.status",
        expected_behavior="successful creation must return HTTP 201.",
        activation={"injected_status": 200},
        ground_truth={"detectable_by": ["expected status assertion"]},
    ),
}


def all_faults() -> list[Fault]:
    return [FAULTS[key] for key in sorted(FAULTS)]


def faults_for_operation(operation_id: str) -> list[Fault]:
    return [fault for fault in all_faults() if fault.operation_id == operation_id]


def fault_by_id(fault_id: str) -> Fault:
    return FAULTS[fault_id]


def _path_segments(path: str) -> list[str]:
    return str(path).split("?", 1)[0].strip("/").split("/")


def _segment_matches(left: str, right: str) -> bool:
    if left == right:
        return True
    return (
        left.startswith("{")
        and left.endswith("}")
        or right.startswith("{")
        and right.endswith("}")
    )


def paths_overlap(spec_path: str, fault_path: str) -> bool:
    """Compare concrete and templated paths without tying faults to IDs."""
    left = _path_segments(spec_path)
    right = _path_segments(fault_path)
    return len(left) == len(right) and all(
        _segment_matches(a, b) for a, b in zip(left, right, strict=False)
    )


def applicable_faults(operations: list[Operation]) -> list[Fault]:
    """Return faults whose method/path can be exercised by the specification."""
    return [
        fault
        for fault in all_faults()
        if any(
            operation.method.upper() == fault.method.upper()
            and paths_overlap(operation.path, fault.path)
            for operation in operations
        )
    ]


def applicable_fault_ids(operations: list[Operation]) -> list[str]:
    return [fault.fault_id for fault in applicable_faults(operations)]
