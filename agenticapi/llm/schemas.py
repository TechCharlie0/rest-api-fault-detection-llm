"""Draft-07 JSON schemas for the four structured LLM tasks.

The schemas leave optional detail permissive (agents may not have every field
available) while still enforcing the core identifiers, technique vocabulary,
and container types that downstream code depends on.
"""

from __future__ import annotations

from typing import Any

from agenticapi.models import Technique

TECHNIQUES = [technique.value for technique in Technique]

REQUEST_STEP_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "method": {"type": "string", "minLength": 1},
        "path": {"type": "string", "minLength": 1},
        "path_params": {"type": "object"},
        "query": {"type": "object"},
        "headers": {
            "type": "object",
            "additionalProperties": {"type": ["string", "number", "boolean"]},
        },
        "body": {},
        "media_type": {"type": "string"},
        "form": {"type": "object"},
        "files": {"type": "object"},
        "auth": {"type": ["string", "null"]},
        "capture": {"type": "object", "additionalProperties": {"type": "string"}},
        "expected_status": {"type": ["integer", "null"]},
        "label": {"type": "string"},
    },
    "required": ["method", "path"],
    "additionalProperties": True,
}

ASSERTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "minLength": 1},
        "target": {"type": "string"},
        "expected": {},
        "description": {"type": "string"},
    },
    "required": ["kind"],
    "additionalProperties": True,
}

TEST_CASE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "case_id": {"type": "string", "minLength": 1},
        "operation_id": {"type": "string", "minLength": 1},
        "technique": {"type": "string", "enum": TECHNIQUES},
        "description": {"type": "string"},
        "steps": {"type": "array", "items": REQUEST_STEP_SCHEMA},
        "assertions": {"type": "array", "items": ASSERTION_SCHEMA},
        "expected_status": {"type": ["integer", "null"]},
        "oracle_rules": {"type": "array", "items": {"type": "string"}},
        "metadata": {"type": "object"},
    },
    "required": ["case_id", "operation_id", "technique"],
    "additionalProperties": True,
}

SPEC_ANALYSIS_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "operations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "operation_id": {"type": "string", "minLength": 1},
                    "purpose": {"type": "string"},
                    "risk_notes": {"type": "array", "items": {"type": "string"}},
                    "test_angles": {"type": "array", "items": {"type": "string"}},
                    "auth_required": {"type": "boolean"},
                },
                "required": ["operation_id"],
                "additionalProperties": True,
            },
        },
        "risk_areas": {"type": "array", "items": {"type": "string"}},
        "auth_notes": {"type": "array", "items": {"type": "string"}},
        "notes": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary"],
    "additionalProperties": True,
}

PLANNING_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "operation_id": {"type": "string", "minLength": 1},
                    "techniques": {
                        "type": "array",
                        "items": {"type": "string", "enum": TECHNIQUES},
                        "minItems": 1,
                    },
                    "priority": {"type": "integer", "minimum": 0},
                    "max_cases": {"type": "integer", "minimum": 1},
                    "rationale": {"type": "string"},
                },
                "required": ["operation_id", "techniques"],
                "additionalProperties": True,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": True,
}


GENERATION_STEP_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "method": {"type": "string", "enum": ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"]},
        "path": {"type": "string", "minLength": 1},
        "headers": {"type": "object"},
        "body": {},
        "auth": {"type": ["string", "null"]},
        "expected_status": {"type": ["integer", "null"]},
    },
    "required": ["method", "path"],
    "additionalProperties": False,
}

GENERATION_TEST_CASE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "case_id": {"type": "string", "minLength": 1},
        "operation_id": {"type": "string", "minLength": 1},
        "technique": {"type": "string", "enum": TECHNIQUES},
        "steps": {
            "type": "array",
            "items": GENERATION_STEP_SCHEMA,
            "minItems": 1,
            "maxItems": 3,
        },
        "expected_status": {"type": ["integer", "null"]},
    },
    "required": ["case_id", "operation_id", "technique", "steps", "expected_status"],
    "additionalProperties": False,
}

GENERATION_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {
        "cases": {
            "type": "array",
            "items": GENERATION_TEST_CASE_SCHEMA,
            "maxItems": 12,
        },
    },
    "required": ["cases"],
    "additionalProperties": True,
}

REPAIR_TEST_CASE_SCHEMA: dict[str, Any] = {
    **TEST_CASE_SCHEMA,
    "properties": {
        **TEST_CASE_SCHEMA["properties"],
        "steps": {"type": "array", "items": REQUEST_STEP_SCHEMA, "minItems": 1},
        "assertions": {"type": "array", "items": ASSERTION_SCHEMA, "minItems": 1},
        "expected_status": {"type": "integer", "minimum": 100, "maximum": 599},
    },
    "required": [
        "case_id",
        "operation_id",
        "technique",
        "steps",
        "assertions",
        "expected_status",
    ],
}

REPAIR_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {
        "cases": {"type": "array", "items": REPAIR_TEST_CASE_SCHEMA},
        "notes": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["cases"],
    "additionalProperties": True,
}

SCHEMAS: dict[str, dict[str, Any]] = {
    "spec_analysis": SPEC_ANALYSIS_SCHEMA,
    "planning": PLANNING_SCHEMA,
    "generation": GENERATION_SCHEMA,
    "repair": REPAIR_SCHEMA,
}


def schema_for(task: str) -> dict[str, Any] | None:
    """Return the schema for ``task`` or ``None`` when no schema is registered."""
    return SCHEMAS.get(task)
