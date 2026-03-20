"""Tests for request ID middleware."""

from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from src.api.middleware.request_id import RequestIDMiddleware


def _make_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)

    @app.get("/test")
    async def test_endpoint(request: Request):
        return {"request_id": request.state.request_id}

    return app


def test_generates_request_id_when_absent():
    client = TestClient(_make_app())
    resp = client.get("/test")
    assert resp.status_code == 200
    rid = resp.headers["X-Request-ID"]
    UUID(rid)  # validates it's a valid UUID


def test_preserves_incoming_request_id():
    client = TestClient(_make_app())
    resp = client.get("/test", headers={"X-Request-ID": "custom-123"})
    assert resp.headers["X-Request-ID"] == "custom-123"
    assert resp.json()["request_id"] == "custom-123"
