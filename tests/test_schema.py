"""Schema sampling, validation, and path lookup tests."""

from __future__ import annotations

from agenticapi.spec.schema import (
    MISSING,
    get_path,
    has_path,
    sample_schema,
    validate_body,
)


def test_sample_ref_schema(shop_spec):
    sampled = sample_schema(
        {"$ref": "#/components/schemas/Product"},
        shop_spec.raw_schemas,
        name_hint="product",
    )
    assert isinstance(sampled, dict)
    assert {"id", "name", "price", "stock", "category"} <= set(sampled)
    assert isinstance(sampled["price"], (int, float))
    assert sampled["category"] in {"electronics", "books", "clothing"}


def test_validate_body_reports_type_error(shop_spec):
    errors = validate_body(
        {"id": "p1", "name": "x", "price": "free", "stock": 1, "category": "books"},
        {"$ref": "#/components/schemas/Product"},
        shop_spec.raw_schemas,
    )
    assert errors
    assert any("price" in error for error in errors)


def test_get_path_and_missing():
    payload = {"body": {"items": [{"id": "x"}]}}
    assert get_path(payload, "body.items[0].id") == "x"
    assert get_path(payload, "body.items[1].id") is MISSING
    assert has_path(payload, "body.items[0].id")
    assert not has_path(payload, "body.nope")
