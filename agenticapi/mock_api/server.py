"""Local, fault-injectable HTTP API.

Only loopback binding is supported.  The server is intentionally small and
deterministic so that experiments are reproducible and never touch public APIs.
"""

from __future__ import annotations

import json
import re
import threading
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from agenticapi.mock_api.store import PRODUCT_CATEGORIES, MockState

PRODUCT_ITEM_RE = re.compile(r"^/products/([^/]+)$")
PRODUCT_IMAGE_RE = re.compile(r"^/products/([^/]+)/image$")
ORDER_ITEM_RE = re.compile(r"^/orders/([^/]+)$")
USER_ITEM_RE = re.compile(r"^/users/([^/]+)$")


class MockRequestHandler(BaseHTTPRequestHandler):
    server_version = "AgenticAPI-Mock/1.0"
    protocol_version = "HTTP/1.1"

    @property
    def state(self) -> MockState:
        return self.server.state  # type: ignore[attr-defined]

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802
        self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch("POST")

    def do_PUT(self) -> None:  # noqa: N802
        self._dispatch("PUT")

    def do_PATCH(self) -> None:  # noqa: N802
        self._dispatch("PATCH")

    def do_DELETE(self) -> None:  # noqa: N802
        self._dispatch("DELETE")

    # ---- request helpers -------------------------------------------------
    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", "0") or "0")
        return self.rfile.read(length) if length else b""

    def _json_body(self) -> dict[str, Any]:
        raw = self._read_body()
        if not raw:
            raise ValueError("request body is required")
        value = json.loads(raw.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("request body must be a JSON object")
        return value

    def _form_body(self) -> dict[str, Any]:
        raw = self._read_body().decode("utf-8")
        return {key: values[-1] if values else "" for key, values in parse_qs(raw).items()}

    def _multipart_body(self) -> dict[str, Any]:
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            raise ValueError("expected multipart/form-data")
        raw = self._read_body()
        message = BytesParser(policy=policy.default).parsebytes(
            b"Content-Type: " + content_type.encode("utf-8") + b"\r\nMIME-Version: 1.0\r\n\r\n" + raw
        )
        result: dict[str, Any] = {}
        if not message.is_multipart():
            raise ValueError("malformed multipart body")
        for part in message.iter_parts():
            name = part.get_param("name", header="content-disposition")
            if not name:
                continue
            payload = part.get_payload(decode=True) or b""
            result[str(name)] = {
                "filename": part.get_filename(),
                "size": len(payload),
                "content": payload,
            }
        return result

    def _send(self, status: int, body: Any = None, extra_headers: dict[str, str] | None = None) -> None:
        payload = b"" if body is None else json.dumps(body).encode("utf-8")
        self.send_response(status)
        if body is not None:
            self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if payload:
            self.wfile.write(payload)

    def _error(self, status: int, code: str, message: str) -> None:
        self._send(status, {"code": code, "message": message})

    def _token(self) -> str | None:
        header = self.headers.get("Authorization", "")
        if header.startswith("Bearer "):
            return header[7:].strip()
        return None

    def _actor(self, *, allow_bypass: bool = False) -> tuple[str | None, str | None, str | None]:
        token = self._token()
        user, error = self.state.authenticate(token)
        if user is not None:
            return str(user["username"]), str(user["role"]), None
        if allow_bypass:
            return "alice", "user", None
        return None, None, error or "authentication required"

    def _fault(self, fault_id: str) -> bool:
        return self.state.active_fault_id == fault_id

    # ---- validation ------------------------------------------------------
    @staticmethod
    def _validate_product(
        payload: dict[str, Any],
        *,
        skip_name: bool = False,
        skip_price: bool = False,
    ) -> str | None:
        name = payload.get("name")
        price = payload.get("price")
        stock = payload.get("stock")
        category = payload.get("category")
        if not skip_name and (not isinstance(name, str) or not name.strip()):
            return "name is required"
        if not skip_price and (
            not isinstance(price, (int, float)) or isinstance(price, bool) or price <= 0
        ):
            return "price must be a positive number"
        if not isinstance(stock, int) or isinstance(stock, bool) or stock < 0:
            return "stock must be a non-negative integer"
        if category not in PRODUCT_CATEGORIES:
            return "category is invalid"
        return None

    @staticmethod
    def _validate_order(payload: dict[str, Any]) -> str | None:
        product_id = payload.get("product_id")
        quantity = payload.get("quantity")
        if not isinstance(product_id, str) or not product_id:
            return "product_id is required"
        if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 1:
            return "quantity must be a positive integer"
        return None

    @staticmethod
    def _valid_user_update(payload: dict[str, Any]) -> str | None:
        name = payload.get("name")
        email = payload.get("email")
        if not isinstance(name, str) or not name.strip():
            return "name is required"
        if not isinstance(email, str) or "@" not in email:
            return "email is invalid"
        return None

    # ---- dispatch --------------------------------------------------------
    def _dispatch(self, method: str) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        self.state.request_count += 1
        try:
            if path == "/health" and method == "GET":
                self._send(200, {"status": "ok"})
            elif path == "/__admin/reset" and method == "POST":
                self.state.reset()
                self._send(204)
            elif path == "/__admin/fault" and method == "POST":
                payload = self._json_body()
                self.state.set_fault(payload.get("fault_id"))
                self._send(200, {"active_fault_id": self.state.active_fault_id})
            elif path == "/__admin/state" and method == "GET":
                self._send(200, self.state.snapshot())
            elif path == "/auth/login" and method == "POST":
                self._login()
            elif path == "/auth/logout" and method == "POST":
                self._logout()
            elif path == "/products":
                if method == "GET":
                    self._list_products(query)
                elif method == "POST":
                    self._create_product()
                else:
                    self._error(405, "method_not_allowed", "method not allowed")
            elif match := PRODUCT_ITEM_RE.match(path):
                self._product_item(method, match.group(1))
            elif match := PRODUCT_IMAGE_RE.match(path):
                if method == "POST":
                    self._upload_image(match.group(1))
                else:
                    self._error(405, "method_not_allowed", "method not allowed")
            elif path == "/orders":
                if method == "GET":
                    self._list_orders()
                elif method == "POST":
                    self._create_order()
                else:
                    self._error(405, "method_not_allowed", "method not allowed")
            elif match := ORDER_ITEM_RE.match(path):
                self._order_item(method, match.group(1))
            elif match := USER_ITEM_RE.match(path):
                self._user_item(method, match.group(1))
            else:
                self._error(404, "not_found", "not found")
        except (ValueError, json.JSONDecodeError) as exc:
            self._error(400, "invalid_request", str(exc))
        except Exception as exc:  # noqa: BLE001
            self._error(500, "internal_error", type(exc).__name__)

    # ---- auth ------------------------------------------------------------
    def _login(self) -> None:
        payload = self._json_body()
        username = payload.get("username")
        password = payload.get("password")
        if not isinstance(username, str) or not isinstance(password, str):
            self._error(400, "invalid_request", "username and password are required")
            return
        result, error = self.state.login(username, password)
        if result is None:
            self._error(401, "unauthorized", error or "invalid credentials")
            return
        self._send(200, result)

    def _logout(self) -> None:
        actor, role, error = self._actor()
        if actor is None:
            self._error(401, "unauthorized", error or "authentication required")
            return
        self._send(204)

    # ---- products --------------------------------------------------------
    def _list_products(self, query: dict[str, list[str]]) -> None:
        category = query.get("category", [None])[-1]
        if category is not None and category not in PRODUCT_CATEGORIES:
            self._error(400, "invalid_query", "invalid category")
            return
        min_price: float | None = None
        if "min_price" in query:
            try:
                min_price = float(query["min_price"][-1])
            except ValueError:
                self._error(400, "invalid_query", "min_price must be numeric")
                return
        limit: int | None = None
        if "limit" in query:
            try:
                limit = int(query["limit"][-1])
            except ValueError:
                self._error(400, "invalid_query", "limit must be an integer")
                return
            if limit < 1 or limit > 100:
                self._error(400, "invalid_query", "limit must be between 1 and 100")
                return
        self._send(200, self.state.list_products(category=category, min_price=min_price, limit=limit))

    def _create_product(self) -> None:
        actor, role, error = self._actor()
        if actor is None:
            self._error(401, "unauthorized", error or "authentication required")
            return
        if role != "admin":
            self._error(403, "forbidden", "admin role required")
            return
        payload = self._json_body()
        skip_name = self._fault("F11")
        skip_price = self._fault("F04")
        validation_error = self._validate_product(
            payload, skip_name=skip_name, skip_price=skip_price
        )
        if validation_error:
            self._error(400, "validation_error", validation_error)
            return
        product = self.state.create_product(payload)
        status = 200 if self._fault("F12") else 201
        self._send(status, product)

    def _product_item(self, method: str, product_id: str) -> None:
        if method == "GET":
            self._get_product(product_id)
        elif method == "PUT":
            self._update_product(product_id)
        elif method == "DELETE":
            self._delete_product(product_id)
        else:
            self._error(405, "method_not_allowed", "method not allowed")

    def _get_product(self, product_id: str) -> None:
        if product_id == "p1" and self._fault("F01"):
            self._error(500, "injected_failure", "injected server failure")
            return
        product = self.state.get_product(product_id, include_deleted=self._fault("F07"))
        if product is None:
            self._error(404, "not_found", "product not found")
            return
        if product_id == "p1" and self._fault("F02"):
            product["price"] = str(product["price"])
        if product_id == "p1" and self._fault("F03"):
            product.pop("name", None)
        if product_id == "p1" and self._fault("F10"):
            product["stock"] = -1
        self._send(200, product)

    def _update_product(self, product_id: str) -> None:
        actor, role, error = self._actor()
        if actor is None:
            self._error(401, "unauthorized", error or "authentication required")
            return
        if role != "admin":
            self._error(403, "forbidden", "admin role required")
            return
        payload = self._json_body()
        validation_error = self._validate_product(payload)
        if validation_error:
            self._error(400, "validation_error", validation_error)
            return
        product = self.state.update_product(product_id, payload)
        if product is None:
            self._error(404, "not_found", "product not found")
            return
        self._send(200, product)

    def _delete_product(self, product_id: str) -> None:
        actor, role, error = self._actor()
        if actor is None:
            self._error(401, "unauthorized", error or "authentication required")
            return
        if role != "admin":
            self._error(403, "forbidden", "admin role required")
            return
        result, message = self.state.delete_product(product_id, inconsistent=self._fault("F07"))
        if result == "missing":
            self._error(404, "not_found", message)
            return
        if result == "conflict":
            self._error(409, "conflict", message)
            return
        self._send(204)

    def _upload_image(self, product_id: str) -> None:
        actor, role, error = self._actor()
        if actor is None:
            self._error(401, "unauthorized", error or "authentication required")
            return
        if role != "admin":
            self._error(403, "forbidden", "admin role required")
            return
        if self.state.get_product(product_id) is None:
            self._error(404, "not_found", "product not found")
            return
        parts = self._multipart_body()
        image = parts.get("image")
        if not image or not image.get("size"):
            self._error(400, "validation_error", "image file is required")
            return
        caption_part = parts.get("caption")
        caption = ""
        if caption_part and caption_part.get("content"):
            caption = caption_part["content"].decode("utf-8", errors="replace")
        self._send(
            200,
            {
                "product_id": product_id,
                "caption": caption,
                "size_bytes": int(image["size"]),
            },
        )

    # ---- orders ----------------------------------------------------------
    def _list_orders(self) -> None:
        bypass = self._fault("F05")
        actor, role, error = self._actor(allow_bypass=bypass)
        if actor is None:
            self._error(401, "unauthorized", error or "authentication required")
            return
        self._send(200, self.state.list_orders(actor=actor, role=str(role)))

    def _create_order(self) -> None:
        actor, role, error = self._actor()
        if actor is None:
            self._error(401, "unauthorized", error or "authentication required")
            return
        payload = self._json_body()
        validation_error = self._validate_order(payload)
        if validation_error:
            self._error(400, "validation_error", validation_error)
            return
        idempotency_key = self.headers.get("Idempotency-Key")
        result, value = self.state.create_order(
            owner=actor,
            product_id=str(payload["product_id"]),
            quantity=int(payload["quantity"]),
            idempotency_key=idempotency_key,
            skip_stock_check=self._fault("F08"),
            ignore_idempotency=self._fault("F09"),
        )
        if result == "missing":
            self._error(404, "not_found", str(value))
            return
        if result == "invalid":
            self._error(400, "validation_error", str(value))
            return
        self._send(201, value)

    def _order_item(self, method: str, order_id: str) -> None:
        actor, role, error = self._actor()
        if actor is None:
            self._error(401, "unauthorized", error or "authentication required")
            return
        order = self.state.get_order(order_id)
        if order is None:
            self._error(404, "not_found", "order not found")
            return
        is_owner = order["owner"] == actor
        if not is_owner and role != "admin" and not (method == "GET" and self._fault("F06")):
            self._error(403, "forbidden", "not the order owner")
            return
        if method == "GET":
            self._send(200, order)
            return
        if method == "PATCH":
            payload = self._json_body()
            status = payload.get("status")
            if not isinstance(status, str):
                self._error(400, "validation_error", "status is required")
                return
            result, value = self.state.update_order(order_id, status)
            if result == "missing":
                self._error(404, "not_found", str(value))
            elif result == "invalid":
                self._error(400, "validation_error", str(value))
            elif result == "conflict":
                self._error(409, "conflict", str(value))
            else:
                self._send(200, value)
            return
        self._error(405, "method_not_allowed", "method not allowed")

    # ---- users -----------------------------------------------------------
    def _user_item(self, method: str, username: str) -> None:
        actor, role, error = self._actor()
        if actor is None:
            self._error(401, "unauthorized", error or "authentication required")
            return
        if actor != username and role != "admin":
            self._error(403, "forbidden", "not the account owner")
            return
        user = self.state.get_user(username)
        if user is None:
            self._error(404, "not_found", "user not found")
            return
        if method == "GET":
            self._send(200, user)
            return
        if method == "PUT":
            payload = self._json_body()
            validation_error = self._valid_user_update(payload)
            if validation_error:
                self._error(400, "validation_error", validation_error)
                return
            updated = self.state.update_user(username, payload)
            if updated is None:
                self._error(404, "not_found", "user not found")
                return
            self._send(200, updated)
            return
        self._error(405, "method_not_allowed", "method not allowed")


class MockAPIServer:
    """Context-managed local mock API server."""

    def __init__(self, host: str = "127.0.0.1", port: int = 0, fault_id: str | None = None) -> None:
        if host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("mock API may only bind to a loopback address")
        self.host = host
        self.port = port
        self.state = MockState()
        self.state.reset(clear_fault=True)
        self.state.set_fault(fault_id)
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        if self._server is None:
            raise RuntimeError("server is not started")
        host = "127.0.0.1" if self.host in {"localhost", "::1"} else self.host
        return f"http://{host}:{self._server.server_address[1]}"

    def start(self) -> MockAPIServer:
        server = ThreadingHTTPServer((self.host, self.port), MockRequestHandler)
        server.state = self.state  # type: ignore[attr-defined]
        server.daemon_threads = True
        self._server = server
        self._thread = threading.Thread(target=server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._server = None
        self._thread = None

    def reset(self, *, clear_fault: bool = False) -> None:
        self.state.reset(clear_fault=clear_fault)

    def set_fault(self, fault_id: str | None) -> None:
        self.state.set_fault(fault_id)

    def __enter__(self) -> MockAPIServer:
        return self.start()

    def __exit__(self, *args: object) -> None:
        self.stop()
