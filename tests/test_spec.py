"""Specification loading, reference resolution, and graph tests."""

from __future__ import annotations

import pytest

from agenticapi.spec.graph import graph_metrics
from agenticapi.spec.loader import normalize_spec
from agenticapi.spec.resolver import resolve_pointer


def test_load_shop_spec(shop_spec):
    assert shop_spec.title == "AgenticAPI Local Shop"
    assert shop_spec.openapi_version == "3.0.3"
    assert len(shop_spec.operations) == 15
    assert "create_order" in shop_spec.operation_map()
    assert shop_spec.operation("create_order").requires_auth
    assert shop_spec.operation("login").request_body is not None
    assert shop_spec.operation("upload_product_image").primary_media_type == "multipart/form-data"


def test_load_swagger2_petstore(petstore_spec):
    assert petstore_spec.openapi_version.startswith("2")
    assert len(petstore_spec.operations) == 20
    assert "addpet" in petstore_spec.operation_map()
    assert petstore_spec.operation("addpet").request_body is not None
    assert "Pet" in petstore_spec.raw_schemas


def test_graph_metrics(shop_spec, shop_graph):
    metrics = graph_metrics(shop_spec, shop_graph)
    assert metrics["operation_nodes"] == 15
    assert metrics["schema_nodes"] == 12
    assert metrics["declared_workflows"] == 3
    assert metrics["auth_edges"] == 11
    assert metrics["operation_edges"] >= 20
    assert set(shop_graph.workflows[0]) >= {"login", "create_order", "get_order"}


def test_resolver_pointer_and_cycles():
    root = {"components": {"schemas": {"A": {"type": "string"}}}}
    assert resolve_pointer(root, "#/components/schemas/A") == {"type": "string"}
    with pytest.raises(ValueError):
        resolve_pointer(root, "#/components/schemas/Missing")


def test_normalize_minimal_spec():
    spec = normalize_spec(
        {
            "openapi": "3.0.0",
            "info": {"title": "Tiny", "version": "1"},
            "paths": {
                "/ping": {
                    "get": {
                        "operationId": "ping",
                        "responses": {"200": {"description": "ok"}},
                    }
                }
            },
        }
    )
    assert spec.title == "Tiny"
    assert [operation.operation_id for operation in spec.operations] == ["ping"]
    assert spec.operation("ping").success_status == "200"
