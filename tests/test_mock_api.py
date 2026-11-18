"""Local mock API behaviour and fault hooks."""

from __future__ import annotations

from typing import Any

import pytest
import requests


def call(
    server,
    method: str,
    path: str,
    *,
    token: str | None = None,
    json: Any = None,
    headers: dict[str, str] | None = None,
) -> requests.Response:
    merged = dict(headers or {})
    if token:
        merged["Authorization"] = f"Bearer {token}"
    return requests.request(method, server.base_url + path, json=json, headers=merged, timeout=5)


@pytest.fixture(autouse=True)
def clean_server(live_server):
    live_server.reset(clear_fault=True)
    yield
    live_server.reset(clear_fault=True)


def test_health_and_login(live_server):
    assert call(live_server, "GET", "/health").json() == {"status": "ok"}
    response = call(
        live_server,
        "POST",
        "/auth/login",
        json={"username": "alice", "password": "alicepw"},
    )
    assert response.status_code == 200
    assert response.json()["token"] == "token-alice"


def test_auth_required(live_server):
    assert call(live_server, "GET", "/orders").status_code == 401
    assert call(live_server, "GET", "/orders", token="token-expired").status_code == 401


def test_admin_product_crud(live_server):
    payload = {
        "name": "Widget",
        "price": 12.5,
        "stock": 3,
        "category": "electronics",
    }
    created = call(live_server, "POST", "/products", token="token-admin", json=payload)
    assert created.status_code == 201
    product_id = created.json()["id"]
    assert call(live_server, "GET", f"/products/{product_id}").status_code == 200
    updated = call(
        live_server,
        "PUT",
        f"/products/{product_id}",
        token="token-admin",
        json={**payload, "price": 13.0},
    )
    assert updated.status_code == 200
    assert updated.json()["price"] == 13.0
    assert call(live_server, "DELETE", f"/products/{product_id}", token="token-admin").status_code == 204


def test_order_idempotency(live_server):
    payload = {"product_id": "p1", "quantity": 1}
    headers = {"Idempotency-Key": "test-key"}
    first = call(live_server, "POST", "/orders", token="token-alice", json=payload, headers=headers)
    second = call(live_server, "POST", "/orders", token="token-alice", json=payload, headers=headers)
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]


def test_f01_f02_f03_f10_product_faults(live_server):
    live_server.set_fault("F01")
    assert call(live_server, "GET", "/products/p1").status_code == 500
    live_server.set_fault("F02")
    assert isinstance(call(live_server, "GET", "/products/p1").json()["price"], str)
    live_server.set_fault("F03")
    assert "name" not in call(live_server, "GET", "/products/p1").json()
    live_server.set_fault("F10")
    assert call(live_server, "GET", "/products/p1").json()["stock"] == -1


def test_f05_f06_auth_faults(live_server):
    live_server.set_fault("F05")
    assert call(live_server, "GET", "/orders").status_code == 200
    live_server.set_fault("F06")
    assert call(live_server, "GET", "/orders/o1", token="token-alice").status_code == 200


def test_f07_delete_inconsistency(live_server):
    live_server.set_fault("F07")
    assert call(live_server, "DELETE", "/products/p3", token="token-admin").status_code == 204
    response = call(live_server, "GET", "/products/p3")
    assert response.status_code == 200
    assert response.json().get("deleted") is True


def test_f08_f09_f11_f12_faults(live_server):
    live_server.set_fault("F08")
    assert (
        call(
            live_server,
            "POST",
            "/orders",
            token="token-alice",
            json={"product_id": "p1", "quantity": 6},
        ).status_code
        == 201
    )
    live_server.set_fault("F09")
    payload = {"product_id": "p2", "quantity": 1}
    headers = {"Idempotency-Key": "dup"}
    first = call(live_server, "POST", "/orders", token="token-alice", json=payload, headers=headers)
    second = call(live_server, "POST", "/orders", token="token-alice", json=payload, headers=headers)
    assert first.json()["id"] != second.json()["id"]
    live_server.set_fault("F11")
    created = call(
        live_server,
        "POST",
        "/products",
        token="token-admin",
        json={"price": 1.0, "stock": 1, "category": "books"},
    )
    assert created.status_code == 201
    live_server.set_fault("F12")
    assert (
        call(
            live_server,
            "POST",
            "/products",
            token="token-admin",
            json={"name": "X", "price": 1.0, "stock": 1, "category": "books"},
        ).status_code
        == 200
    )
