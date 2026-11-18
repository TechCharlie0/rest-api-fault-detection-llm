"""Thread-safe in-memory state for the local shop API."""

from __future__ import annotations

import threading
import time
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

TOKEN_MAP = {
    "token-alice": ("alice", "user", None),
    "token-bob": ("bob", "user", None),
    "token-admin": ("admin", "admin", None),
    "token-expired": ("alice", "user", 1),
}
USER_PASSWORDS = {
    "alice": "alicepw",
    "bob": "bobpw",
    "admin": "adminpw",
}
USER_TOKENS = {
    "alice": "token-alice",
    "bob": "token-bob",
    "admin": "token-admin",
}
PRODUCT_CATEGORIES = {"electronics", "books", "clothing"}
ORDER_STATUSES = {"pending", "paid", "shipped"}
ALLOWED_TRANSITIONS = {
    "pending": {"paid"},
    "paid": {"shipped"},
    "shipped": set(),
}


class StoreError(ValueError):
    pass


@dataclass
class MockState:
    lock: threading.RLock = field(default_factory=threading.RLock)
    products: dict[str, dict[str, Any]] = field(default_factory=dict)
    orders: dict[str, dict[str, Any]] = field(default_factory=dict)
    users: dict[str, dict[str, Any]] = field(default_factory=dict)
    idempotency: dict[str, str] = field(default_factory=dict)
    active_fault_id: str | None = None
    product_seq: int = 4
    order_seq: int = 3
    request_count: int = 0

    def reset(self, *, clear_fault: bool = False) -> None:
        with self.lock:
            fault = None if clear_fault else self.active_fault_id
            self.products = {
                "p1": {
                    "id": "p1",
                    "name": "Laptop",
                    "price": 999.99,
                    "stock": 5,
                    "category": "electronics",
                },
                "p2": {
                    "id": "p2",
                    "name": "Novel",
                    "price": 19.99,
                    "stock": 10,
                    "category": "books",
                },
                "p3": {
                    "id": "p3",
                    "name": "T-Shirt",
                    "price": 15.0,
                    "stock": 0,
                    "category": "clothing",
                },
            }
            self.orders = {
                "o1": {
                    "id": "o1",
                    "product_id": "p1",
                    "quantity": 1,
                    "status": "pending",
                    "total": 999.99,
                    "owner": "bob",
                },
                "o2": {
                    "id": "o2",
                    "product_id": "p2",
                    "quantity": 1,
                    "status": "paid",
                    "total": 19.99,
                    "owner": "alice",
                },
            }
            self.users = {
                "alice": {
                    "username": "alice",
                    "name": "Alice",
                    "email": "alice@example.com",
                    "role": "user",
                },
                "bob": {
                    "username": "bob",
                    "name": "Bob",
                    "email": "bob@example.com",
                    "role": "user",
                },
                "admin": {
                    "username": "admin",
                    "name": "Admin",
                    "email": "admin@example.com",
                    "role": "admin",
                },
            }
            self.idempotency = {}
            self.active_fault_id = fault
            self.product_seq = 4
            self.order_seq = 3
            self.request_count = 0

    def set_fault(self, fault_id: str | None) -> None:
        with self.lock:
            self.active_fault_id = fault_id

    def fault(self) -> str | None:
        return self.active_fault_id

    def authenticate(self, token: str | None) -> tuple[dict[str, Any] | None, str | None]:
        if not token:
            return None, "missing token"
        entry = TOKEN_MAP.get(token)
        if entry is None:
            return None, "invalid token"
        username, _role, expires_at = entry
        if expires_at is not None and expires_at <= time.time():
            return None, "expired token"
        user = self.users.get(username)
        if user is None:
            return None, "unknown user"
        return deepcopy(user), None

    def login(self, username: str, password: str) -> tuple[dict[str, Any] | None, str | None]:
        with self.lock:
            if USER_PASSWORDS.get(username) != password:
                return None, "invalid credentials"
            user = self.users.get(username)
            if user is None:
                return None, "unknown user"
            return {
                "token": USER_TOKENS[username],
                "role": user["role"],
            }, None

    def list_products(
        self,
        *,
        category: str | None = None,
        min_price: float | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        with self.lock:
            products = [
                deepcopy(product)
                for product in self.products.values()
                if not product.get("deleted")
            ]
        if category:
            products = [p for p in products if p["category"] == category]
        if min_price is not None:
            products = [p for p in products if float(p["price"]) >= min_price]
        if limit is not None:
            products = products[:limit]
        return products

    def get_product(self, product_id: str, *, include_deleted: bool = False) -> dict[str, Any] | None:
        with self.lock:
            product = self.products.get(product_id)
            if product is None:
                return None
            if product.get("deleted") and not include_deleted:
                return None
            return deepcopy(product)

    def create_product(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            product_id = f"p{self.product_seq}"
            self.product_seq += 1
            product = {
                "id": product_id,
                "name": payload.get("name", ""),
                "price": payload.get("price", 0.0),
                "stock": payload.get("stock", 0),
                "category": payload.get("category", ""),
            }
            self.products[product_id] = product
            return deepcopy(product)

    def update_product(self, product_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        with self.lock:
            product = self.products.get(product_id)
            if product is None or product.get("deleted"):
                return None
            product.update(
                {
                    "name": payload.get("name", product["name"]),
                    "price": payload.get("price", product["price"]),
                    "stock": payload.get("stock", product["stock"]),
                    "category": payload.get("category", product["category"]),
                }
            )
            return deepcopy(product)

    def delete_product(self, product_id: str, *, inconsistent: bool = False) -> tuple[str, str]:
        with self.lock:
            product = self.products.get(product_id)
            if product is None or (product.get("deleted") and not inconsistent):
                return "missing", "product not found"
            if any(order["product_id"] == product_id for order in self.orders.values()):
                return "conflict", "product is referenced by an order"
            if inconsistent:
                product["deleted"] = True
            else:
                del self.products[product_id]
            return "deleted", ""

    def product_referenced(self, product_id: str) -> bool:
        with self.lock:
            return any(order["product_id"] == product_id for order in self.orders.values())

    def create_order(
        self,
        *,
        owner: str,
        product_id: str,
        quantity: int,
        idempotency_key: str | None,
        skip_stock_check: bool = False,
        ignore_idempotency: bool = False,
    ) -> tuple[str, Any]:
        with self.lock:
            if idempotency_key and not ignore_idempotency and idempotency_key in self.idempotency:
                existing_id = self.idempotency[idempotency_key]
                existing = self.orders.get(existing_id)
                if existing:
                    return "ok", deepcopy(existing)
            product = self.products.get(product_id)
            if product is None or product.get("deleted"):
                return "missing", "product not found"
            if not skip_stock_check and int(quantity) > int(product["stock"]):
                return "invalid", "insufficient stock"
            if int(product["stock"]) <= 0:
                return "invalid", "out of stock"
            order_id = f"o{self.order_seq}"
            self.order_seq += 1
            order = {
                "id": order_id,
                "product_id": product_id,
                "quantity": int(quantity),
                "status": "pending",
                "total": round(float(product["price"]) * int(quantity), 2),
                "owner": owner,
            }
            self.orders[order_id] = order
            product["stock"] = int(product["stock"]) - int(quantity)
            if idempotency_key and not ignore_idempotency:
                self.idempotency[idempotency_key] = order_id
            return "ok", deepcopy(order)

    def list_orders(self, *, actor: str, role: str) -> list[dict[str, Any]]:
        with self.lock:
            orders = list(self.orders.values())
            if role != "admin":
                orders = [order for order in orders if order["owner"] == actor]
            return [deepcopy(order) for order in orders]

    def get_order(self, order_id: str) -> dict[str, Any] | None:
        with self.lock:
            order = self.orders.get(order_id)
            return deepcopy(order) if order else None

    def update_order(self, order_id: str, status: str) -> tuple[str, Any]:
        with self.lock:
            order = self.orders.get(order_id)
            if order is None:
                return "missing", "order not found"
            if status not in ORDER_STATUSES:
                return "invalid", "invalid status"
            if status not in ALLOWED_TRANSITIONS.get(order["status"], set()):
                return "conflict", f"illegal transition {order['status']} -> {status}"
            order["status"] = status
            return "ok", deepcopy(order)

    def get_user(self, username: str) -> dict[str, Any] | None:
        with self.lock:
            user = self.users.get(username)
            return deepcopy(user) if user else None

    def update_user(self, username: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        with self.lock:
            user = self.users.get(username)
            if user is None:
                return None
            user.update({"name": payload["name"], "email": payload["email"]})
            return deepcopy(user)

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "products": deepcopy(self.products),
                "orders": deepcopy(self.orders),
                "users": deepcopy(self.users),
                "active_fault_id": self.active_fault_id,
                "request_count": self.request_count,
            }
