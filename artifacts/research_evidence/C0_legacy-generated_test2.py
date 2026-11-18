"""Generated AgenticAPI test: create_product__functional."""

from __future__ import annotations

import os

from agenticapi.execution.executor import ExecutionEngine
from agenticapi.execution.serialization import case_from_dict

CASE = case_from_dict({
  "assertions": [
    {
      "description": "HTTP status",
      "expected": 201,
      "kind": "status",
      "target": ""
    },
    {
      "description": "response body matches the declared schema",
      "expected": null,
      "kind": "schema",
      "target": "201"
    }
  ],
  "case_id": "create_product__functional",
  "description": "Valid request for create_product",
  "expected_status": 201,
  "generated_by": "deterministic",
  "metadata": {
    "suite": "C0_legacy"
  },
  "operation_id": "create_product",
  "oracle_rules": [],
  "steps": [
    {
      "auth": "admin",
      "body": {
        "category": "electronics",
        "name": "Generated Widget",
        "price": 12.5,
        "stock": 9
      },
      "capture": {},
      "expected_status": 201,
      "files": {},
      "form": {},
      "headers": {},
      "label": "create_product",
      "media_type": "application/json",
      "method": "POST",
      "path": "/products",
      "path_params": {},
      "query": {}
    }
  ],
  "technique": "functional"
})

def test_create_product__functional() -> None:
    base_url = os.environ.get("AGENTICAPI_BASE_URL", "http://127.0.0.1:8000")
    record = ExecutionEngine(base_url).execute(CASE)
    assert not record.error, record.error
    assert len(record.steps) == len(CASE.steps)
    for observed, planned in zip(record.steps, CASE.steps):
        assert observed.status_code is not None, observed.error
        if planned.expected_status is not None:
            assert observed.status_code == planned.expected_status, (
                f"step {observed.index}: expected {planned.expected_status}, "
                f"got {observed.status_code}"
            )
