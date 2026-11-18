"""Deterministic schema sampling and response validation."""

from __future__ import annotations

from typing import Any

from jsonschema import Draft7Validator, FormatChecker

_MISSING = object()


def resolve_schema(schema: Any, schemas: dict[str, Any], depth: int = 0) -> Any:
    if depth > 20 or not isinstance(schema, dict):
        return schema
    ref = schema.get("$ref")
    if isinstance(ref, str):
        name = ref.rsplit("/", 1)[-1]
        target = schemas.get(name)
        if target is None:
            return schema
        merged = resolve_schema(target, schemas, depth + 1)
        if isinstance(merged, dict):
            extra = {k: v for k, v in schema.items() if k != "$ref"}
            return {**merged, **extra}
        return merged
    return schema


def sample_schema(
    schema: Any,
    schemas: dict[str, Any],
    *,
    name_hint: str = "",
    depth: int = 0,
) -> Any:
    if depth > 8 or not isinstance(schema, dict):
        return None
    schema = resolve_schema(schema, schemas, depth)
    if not isinstance(schema, dict):
        return None
    if "example" in schema:
        return schema["example"]
    if "default" in schema:
        return schema["default"]
    if "const" in schema:
        return schema["const"]
    if "enum" in schema and schema["enum"]:
        return schema["enum"][0]
    if "allOf" in schema:
        merged: dict[str, Any] = {}
        for part in schema["allOf"]:
            value = sample_schema(part, schemas, name_hint=name_hint, depth=depth + 1)
            if isinstance(value, dict):
                merged.update(value)
        return merged
    for key in ("oneOf", "anyOf"):
        if schema.get(key):
            return sample_schema(schema[key][0], schemas, name_hint=name_hint, depth=depth + 1)
    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        schema_type = next((t for t in schema_type if t != "null"), "string")
    if schema_type == "object" or "properties" in schema:
        properties = schema.get("properties") or {}
        required = schema.get("required") or list(properties)
        result: dict[str, Any] = {}
        for key, child in properties.items():
            if key not in required and depth > 0:
                continue
            result[key] = sample_schema(child, schemas, name_hint=key, depth=depth + 1)
        return result
    if schema_type == "array":
        count = 1
        if schema.get("minItems"):
            count = min(int(schema["minItems"]), 3)
        return [
            sample_schema(schema.get("items", {}), schemas, name_hint=name_hint, depth=depth + 1)
            for _ in range(max(count, 1))
        ]
    if schema_type == "string" or schema_type is None:
        fmt = str(schema.get("format", ""))
        if fmt == "email":
            return "sample@example.com"
        if fmt == "date-time":
            return "2025-01-01T00:00:00Z"
        if fmt == "date":
            return "2025-01-01"
        if fmt == "uuid":
            return "00000000-0000-4000-8000-000000000000"
        if fmt == "binary":
            return "sample-bytes"
        if fmt == "uri":
            return "https://example.com/sample"
        if fmt == "password":
            return "sample-password"
        min_length = int(schema.get("minLength", 1) or 1)
        return "sample" + ("x" * max(0, min_length - len("sample")))
    if schema_type == "integer":
        minimum = schema.get("minimum")
        value = int(minimum) if isinstance(minimum, (int, float)) else 1
        if schema.get("exclusiveMinimum") is True and isinstance(minimum, (int, float)):
            value = int(minimum) + 1
        elif isinstance(schema.get("exclusiveMinimum"), (int, float)):
            value = int(schema["exclusiveMinimum"]) + 1
        maximum = schema.get("maximum")
        if isinstance(maximum, (int, float)) and value > maximum:
            value = int(maximum)
        return value
    if schema_type == "number":
        minimum = schema.get("minimum")
        value = float(minimum) if isinstance(minimum, (int, float)) else 1.0
        if value <= 0:
            value = 1.0
        maximum = schema.get("maximum")
        if isinstance(maximum, (int, float)) and value > maximum:
            value = float(maximum)
        return value
    if schema_type == "boolean":
        return True
    if schema_type == "null":
        return None
    return "sample"


def validate_body(body: Any, schema: Any, schemas: dict[str, Any]) -> list[str]:
    if not schema:
        return []
    resolved = resolve_schema(schema, schemas)
    if not isinstance(resolved, dict):
        return []
    validator = Draft7Validator(resolved, format_checker=FormatChecker())
    errors: list[str] = []
    for error in sorted(validator.iter_errors(body), key=lambda e: list(e.path)):
        path = "$" + "".join(f"[{p!r}]" for p in error.path)
        errors.append(f"{path}: {error.message}")
    return errors


def get_path(value: Any, path: str) -> Any:
    if not path:
        return value
    cleaned = path.strip()
    if cleaned.startswith("$"):
        cleaned = cleaned[1:]
    cleaned = cleaned.lstrip(".")
    current = value
    for part in cleaned.split(".") if cleaned else []:
        if not part:
            continue
        while "[" in part and part.endswith("]"):
            name, _, index = part.partition("[")
            if name:
                if not isinstance(current, dict) or name not in current:
                    return _MISSING
                current = current[name]
            try:
                current = current[int(index[:-1])]
            except (TypeError, ValueError, IndexError):
                return _MISSING
            part = ""
        if part:
            if not isinstance(current, dict) or part not in current:
                return _MISSING
            current = current[part]
    return current


def has_path(value: Any, path: str) -> bool:
    return get_path(value, path) is not _MISSING


def type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


MISSING = _MISSING
