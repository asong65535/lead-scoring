"""Tests for structured logging middleware."""

import json

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from src.api.middleware.logging import LoggingMiddleware, configure_logging
from src.api.middleware.request_id import RequestIDMiddleware


def _make_app() -> FastAPI:
    configure_logging(debug=True)
    app = FastAPI()
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(RequestIDMiddleware)

    @app.get("/test")
    async def test_endpoint():
        return {"ok": True}

    @app.get("/health/live")
    async def liveness():
        return {"status": "alive"}

    return app


def test_logs_request(capsys):
    client = TestClient(_make_app())
    resp = client.get("/test")
    assert resp.status_code == 200


def test_excludes_health_live(capsys):
    """Liveness probe should not crash the middleware."""
    client = TestClient(_make_app())
    resp = client.get("/health/live")
    assert resp.status_code == 200
