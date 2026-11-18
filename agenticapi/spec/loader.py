"""Load Swagger 2.0 and OpenAPI 3.x documents into a canonical APISpec."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from agenticapi.models import (
    APISpec,
    Operation,
    Parameter,
    RequestBody,
    ResponseSpec,
    SecurityRequirement,
    SecurityScheme,
)
from agenticapi.spec.resolver import RefResolutionError, resolve

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}
PARAM_SCHEMA_KEYS = {
    "type",
    "format",
    "items",
    "enum",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "minLength",
    "maxLength",
    "pattern",
    "default",
    "example",
    "multipleOf",
    "minItems",
    "maxItems",
    "uniqueItems",
}


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").lower()
    return cleaned or "operation"


def _unique_id(base: str, used: set[str]) -> str:
    candidate = _slug(base)
    if candidate not in used:
        used.add(candidate)
        return candidate
    index = 2
    while f"{candidate}_{index}" in used:
        index += 1
    result = f"{candidate}_{index}"
    used.add(result)
    return result


def _param_schema(data: dict[str, Any]) -> dict[str, Any]:
    schema = {key: data[key] for key in PARAM_SCHEMA_KEYS if key in data}
    if "schema" in data and isinstance(data["schema"], dict):
        schema = dict(data["schema"])
    if "description" in data:
        schema.setdefault("description", data["description"])
    return schema


def _security_requirements(value: Any) -> list[SecurityRequirement]:
    if not isinstance(value, list):
        return []
    result: list[SecurityRequirement] = []
    for requirement in value:
        if not isinstance(requirement, dict):
            continue
        for scheme, scopes in requirement.items():
            result.append(SecurityRequirement(scheme=scheme, scopes=list(scopes or [])))
    return result


def _swagger_security_scheme(name: str, data: dict[str, Any]) -> SecurityScheme:
    return SecurityScheme(
        name=name,
        type=str(data.get("type", "")),
        scheme=str(data.get("scheme", "")),
        bearer_format=str(data.get("bearerFormat", "")),
        flows=dict(data.get("flow", {})) if isinstance(data.get("flow"), dict) else {},
        location=str(data.get("in", "")),
        parameter_name=str(data.get("name", "")),
    )


def _openapi_security_scheme(name: str, data: dict[str, Any]) -> SecurityScheme:
    return SecurityScheme(
        name=name,
        type=str(data.get("type", "")),
        scheme=str(data.get("scheme", "")),
        bearer_format=str(data.get("bearerFormat", "")),
        flows=dict(data.get("flows", {})) if isinstance(data.get("flows"), dict) else {},
        location=str(data.get("in", "")),
        parameter_name=str(data.get("name", "")),
    )


def _swagger_response(
    code: str,
    data: dict[str, Any],
    produces: list[str],
    raw: dict[str, Any],
) -> ResponseSpec:
    data = resolve(data, raw)
    schema = data.get("schema", {})
    content: dict[str, dict[str, Any]] = {}
    if schema:
        for media_type in produces or ["application/json"]:
            content[media_type] = {"schema": resolve(schema, raw)}
    return ResponseSpec(
        status_code=str(code),
        description=str(data.get("description", "")),
        content=content,
        headers=resolve(data.get("headers", {}), raw),
    )


def _openapi_response(code: str, data: dict[str, Any], raw: dict[str, Any]) -> ResponseSpec:
    data = resolve(data, raw)
    content: dict[str, dict[str, Any]] = {}
    for media_type, media in (data.get("content") or {}).items():
        media = resolve(media, raw)
        content[media_type] = {
            "schema": resolve(media.get("schema", {}), raw),
            "example": media.get("example"),
        }
    return ResponseSpec(
        status_code=str(code),
        description=str(data.get("description", "")),
        content=content,
        headers=resolve(data.get("headers", {}), raw),
    )


def _swagger_request_body(
    operation: dict[str, Any],
    raw: dict[str, Any],
) -> RequestBody | None:
    params = operation.get("parameters") or []
    body_param = next((p for p in params if isinstance(p, dict) and p.get("in") == "body"), None)
    form_params = [p for p in params if isinstance(p, dict) and p.get("in") == "formData"]
    consumes = operation.get("consumes") or raw.get("consumes") or []
    if body_param:
        body_param = resolve(body_param, raw)
        media_types = consumes or ["application/json"]
        return RequestBody(
            required=bool(body_param.get("required", False)),
            content={
                media_type: {"schema": resolve(body_param.get("schema", {}), raw)}
                for media_type in media_types
            },
            description=str(body_param.get("description", "")),
        )
    if form_params:
        has_file = any(p.get("type") == "file" for p in form_params)
        media_types = consumes or (
            ["multipart/form-data"] if has_file else ["application/x-www-form-urlencoded"]
        )
        properties: dict[str, Any] = {}
        required: list[str] = []
        for param in form_params:
            param = resolve(param, raw)
            properties[str(param.get("name", ""))] = _param_schema(param)
            if param.get("required"):
                required.append(str(param.get("name", "")))
        schema: dict[str, Any] = {"type": "object", "properties": properties}
        if required:
            schema["required"] = required
        return RequestBody(
            required=bool(required),
            content={media_type: {"schema": schema} for media_type in media_types},
            description="Swagger formData request body",
        )
    return None


def _openapi_request_body(operation: dict[str, Any], raw: dict[str, Any]) -> RequestBody | None:
    body = operation.get("requestBody")
    if not body:
        return None
    body = resolve(body, raw)
    content: dict[str, dict[str, Any]] = {}
    for media_type, media in (body.get("content") or {}).items():
        media = resolve(media, raw)
        content[media_type] = {
            "schema": resolve(media.get("schema", {}), raw),
            "example": media.get("example"),
        }
    return RequestBody(
        required=bool(body.get("required", False)),
        content=content,
        description=str(body.get("description", "")),
    )


def _swagger_parameters(
    operation: dict[str, Any],
    path_item: dict[str, Any],
    raw: dict[str, Any],
) -> list[Parameter]:
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for source in (path_item.get("parameters") or [], operation.get("parameters") or []):
        for param in source:
            if not isinstance(param, dict):
                continue
            resolved = resolve(param, raw)
            key = (str(resolved.get("name", "")), str(resolved.get("in", "")))
            merged[key] = resolved
    result: list[Parameter] = []
    for (name, location), param in merged.items():
        if location == "body":
            continue
        if location == "formData":
            result.append(
                Parameter(
                    name=name,
                    location="formData",
                    required=bool(param.get("required", False)),
                    schema=_param_schema(param),
                    description=str(param.get("description", "")),
                    example=param.get("example"),
                )
            )
            continue
        result.append(
            Parameter(
                name=name,
                location=location,
                required=bool(param.get("required", False)),
                schema=_param_schema(param),
                description=str(param.get("description", "")),
                example=param.get("example"),
            )
        )
    return result


def _openapi_parameters(
    operation: dict[str, Any],
    path_item: dict[str, Any],
    raw: dict[str, Any],
) -> list[Parameter]:
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for source in (path_item.get("parameters") or [], operation.get("parameters") or []):
        for param in source:
            if not isinstance(param, dict):
                continue
            resolved = resolve(param, raw)
            key = (str(resolved.get("name", "")), str(resolved.get("in", "")))
            merged[key] = resolved
    result: list[Parameter] = []
    for (name, location), param in merged.items():
        result.append(
            Parameter(
                name=name,
                location=location,
                required=bool(param.get("required", False)),
                schema=resolve(param.get("schema", {}), raw),
                description=str(param.get("description", "")),
                example=param.get("example"),
            )
        )
    return result


def _spec_base_url_swagger(raw: dict[str, Any]) -> str:
    host = raw.get("host")
    base_path = str(raw.get("basePath", "") or "")
    schemes = raw.get("schemes") or ["http"]
    if host:
        scheme = str(schemes[0]) if schemes else "http"
        return f"{scheme}://{host}{base_path}".rstrip("/")
    return f"http://localhost{base_path}".rstrip("/")


def _spec_base_url_openapi(raw: dict[str, Any]) -> str:
    servers = raw.get("servers") or []
    if not servers:
        return "http://localhost"
    url = str(servers[0].get("url", "")).rstrip("/")
    if url.startswith("/"):
        return f"http://localhost{url}".rstrip("/")
    parsed = urlparse(url)
    if parsed.scheme and parsed.netloc:
        return url
    return "http://localhost"


def _operation_extensions(data: dict[str, Any], path_item: dict[str, Any]) -> dict[str, Any]:
    extensions: dict[str, Any] = {}
    for source in (path_item, data):
        for key, value in source.items():
            if key.startswith("x-"):
                extensions[key] = value
    return extensions


def normalize_spec(raw: dict[str, Any], source_path: str = "") -> APISpec:
    if not isinstance(raw, dict):
        raise ValueError("specification root must be an object")
    used_ids: set[str] = set()
    operations: list[Operation] = []
    is_swagger = str(raw.get("swagger", "")).startswith("2")
    if is_swagger:
        raw_schemas = dict(raw.get("definitions") or {})
        resolved_schemas = resolve(raw_schemas, raw)
        schemes = {
            name: _swagger_security_scheme(name, data)
            for name, data in (raw.get("securityDefinitions") or {}).items()
        }
        global_security = _security_requirements(raw.get("security"))
        base_url = _spec_base_url_swagger(raw)
        version = str(raw.get("swagger", "2.0"))
    else:
        components = raw.get("components") or {}
        raw_schemas = dict(components.get("schemas") or {})
        resolved_schemas = resolve(raw_schemas, raw)
        schemes = {
            name: _openapi_security_scheme(name, data)
            for name, data in (components.get("securitySchemes") or {}).items()
        }
        global_security = _security_requirements(raw.get("security"))
        base_url = _spec_base_url_openapi(raw)
        version = str(raw.get("openapi", "3.0.0"))

    for path, path_item in (raw.get("paths") or {}).items():
        if not isinstance(path_item, dict):
            continue
        for method, operation_data in path_item.items():
            if method.lower() not in HTTP_METHODS or not isinstance(operation_data, dict):
                continue
            method_upper = method.upper()
            raw_id = str(operation_data.get("operationId") or f"{method}_{path}")
            operation_id = _unique_id(raw_id, used_ids)
            if is_swagger:
                parameters = _swagger_parameters(operation_data, path_item, raw)
                request_body = _swagger_request_body(operation_data, raw)
                produces = operation_data.get("produces") or raw.get("produces") or []
                responses = {
                    str(code): _swagger_response(str(code), data, produces, raw)
                    for code, data in (operation_data.get("responses") or {}).items()
                }
            else:
                parameters = _openapi_parameters(operation_data, path_item, raw)
                request_body = _openapi_request_body(operation_data, raw)
                responses = {
                    str(code): _openapi_response(str(code), data, raw)
                    for code, data in (operation_data.get("responses") or {}).items()
                }
            security = _security_requirements(operation_data.get("security")) or global_security
            operations.append(
                Operation(
                    operation_id=operation_id,
                    method=method_upper,
                    path=str(path),
                    summary=str(operation_data.get("summary", "")),
                    description=str(operation_data.get("description", "")),
                    tags=[str(tag) for tag in (operation_data.get("tags") or [])],
                    parameters=parameters,
                    request_body=request_body,
                    responses=responses,
                    security=security,
                    servers=[base_url],
                    extensions=_operation_extensions(operation_data, path_item),
                )
            )

    info = raw.get("info") or {}
    root_extensions = {k: v for k, v in raw.items() if k.startswith("x-")}
    return APISpec(
        title=str(info.get("title", "Untitled API")),
        version=str(info.get("version", "0.0.0")),
        openapi_version=version,
        base_url=base_url,
        operations=operations,
        schemas=resolved_schemas if isinstance(resolved_schemas, dict) else {},
        raw_schemas=raw_schemas,
        security_schemes=schemes,
        extensions=root_extensions,
        source_path=source_path,
    )


def load_spec(path: str | Path) -> APISpec:
    path = Path(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    try:
        return normalize_spec(raw, str(path))
    except RefResolutionError as exc:
        raise ValueError(f"failed to resolve refs in {path}: {exc}") from exc
