"""Meaningful schema and operation dependency graphs.

Every metric exported here has a definition in the returned metrics dictionary.
The graph is intentionally small and inspectable: it models schema references,
resource CRUD relationships, authentication dependencies, and declared workflows.
"""

from __future__ import annotations

import re
from typing import Any

from agenticapi.models import APISpec, DependencyGraph, GraphEdge, Operation


def _ref_name(ref: str) -> str:
    return ref.rsplit("/", 1)[-1]


def _collect_raw_refs(value: Any) -> set[str]:
    refs: set[str] = set()
    if isinstance(value, dict):
        ref = value.get("$ref")
        if isinstance(ref, str):
            refs.add(_ref_name(ref))
        for child in value.values():
            refs.update(_collect_raw_refs(child))
    elif isinstance(value, list):
        for child in value:
            refs.update(_collect_raw_refs(child))
    return refs


def _resource_base(path: str) -> str:
    return re.sub(r"/\{[^}]+\}.*$", "", path).rstrip("/") or "/"


def _schema_depth(schemas: dict[str, Any], name: str, seen: tuple[str, ...] = ()) -> int:
    if name in seen or name not in schemas:
        return 0
    refs = _collect_raw_refs(schemas[name])
    if not refs:
        return 1
    return 1 + max(_schema_depth(schemas, ref, seen + (name,)) for ref in refs)


def _workflows(spec: APISpec) -> list[list[str]]:
    raw = spec.extensions.get("x-agenticapi-workflows", [])
    if not isinstance(raw, list):
        return []
    known = set(spec.operation_map())
    result: list[list[str]] = []
    for workflow in raw:
        if not isinstance(workflow, list):
            continue
        valid = [str(op) for op in workflow if str(op) in known]
        if len(valid) >= 2:
            result.append(valid)
    return result


def _is_protected(operation: Operation) -> bool:
    return bool(operation.security)


def build_dependency_graph(spec: APISpec) -> DependencyGraph:
    graph = DependencyGraph()
    schema_edges: set[tuple[str, str, str]] = set()
    for name, schema in spec.raw_schemas.items():
        for ref in _collect_raw_refs(schema):
            if ref in spec.raw_schemas and ref != name:
                schema_edges.add((name, ref, "schema_ref"))
    graph.schema_edges = [GraphEdge(*edge) for edge in sorted(schema_edges)]

    op_edges: set[tuple[str, str, str, str]] = set()
    operations = spec.operations
    login_ops = [
        op for op in operations if op.operation_id in {"login", "auth_login"} or "/auth/login" in op.path
    ]
    for op in operations:
        if not _is_protected(op):
            continue
        for login_op in login_ops:
            if login_op.operation_id != op.operation_id:
                op_edges.add((login_op.operation_id, op.operation_id, "auth", "login required"))

    for source in operations:
        source_base = _resource_base(source.path)
        for target in operations:
            if source.operation_id == target.operation_id:
                continue
            target_base = _resource_base(target.path)
            if source_base != target_base:
                continue
            if source.method == "POST" and target.path != source.path:
                op_edges.add(
                    (source.operation_id, target.operation_id, "crud", "create before item operation")
                )
            if "{" in source.path and "{" in target.path and target.method in {"PUT", "PATCH", "DELETE"}:
                op_edges.add(
                    (source.operation_id, target.operation_id, "crud", "item read before mutation")
                )

    for workflow in _workflows(spec):
        graph.workflows.append(workflow)
        for left, right in zip(workflow, workflow[1:], strict=False):
            op_edges.add((left, right, "workflow", "declared workflow sequence"))

    graph.operation_edges = [
        GraphEdge(source, target, kind, reason)
        for source, target, kind, reason in sorted(op_edges)
    ]
    graph.auth_edges = [e for e in graph.operation_edges if e.kind == "auth"]
    return graph


def graph_metrics(spec: APISpec, graph: DependencyGraph) -> dict[str, Any]:
    schema_nodes = len(spec.raw_schemas)
    schema_depths = [_schema_depth(spec.raw_schemas, name) for name in spec.raw_schemas]
    out_degrees = [graph.out_degree(op.operation_id) for op in spec.operations]
    in_degrees = [graph.in_degree(op.operation_id) for op in spec.operations]
    return {
        "schema_nodes": schema_nodes,
        "schema_edges": len(graph.schema_edges),
        "max_schema_depth": max(schema_depths, default=0),
        "avg_schema_depth": round(sum(schema_depths) / len(schema_depths), 2) if schema_depths else 0.0,
        "operation_nodes": len(spec.operations),
        "operation_edges": len(graph.operation_edges),
        "auth_edges": len(graph.auth_edges),
        "max_operation_out_degree": max(out_degrees, default=0),
        "max_operation_in_degree": max(in_degrees, default=0),
        "auth_protected_operations": sum(1 for op in spec.operations if _is_protected(op)),
        "declared_workflows": len(graph.workflows),
        "definitions": {
            "schema_nodes": "Number of named schemas in the specification.",
            "schema_edges": "Number of distinct schema-to-schema $ref dependencies.",
            "max_schema_depth": "Maximum number of schema-reference hops from a named schema.",
            "operation_edges": "Number of distinct operation dependency edges (CRUD, auth, workflow).",
            "max_operation_out_degree": "Maximum number of outgoing dependency edges for an operation.",
            "max_operation_in_degree": "Maximum number of incoming dependency edges for an operation.",
            "auth_edges": "Number of login-to-protected-operation edges.",
            "declared_workflows": "Number of x-agenticapi-workflows sequences in the specification.",
        },
    }
