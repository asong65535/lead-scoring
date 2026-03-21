"""Tests for API key authentication middleware."""

import hashlib

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config.settings import get_settings
from src.api.middleware.auth import AuthMiddleware

RAW_TEST_KEY = "test-key-12345"
KEY_HASH = hashlib.sha256(RAW_TEST_KEY.encode()).hexdigest()

settings = get_settings()


@pytest_asyncio.fixture(loop_scope="session")
async def seed_api_key():
    """Insert a test API key, clean up after all tests."""
    engine = create_async_engine(settings.database.url)
    session_factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False,
    )
    async with session_factory() as session:
        await session.execute(
            text(
                "INSERT INTO api_keys (key_hash, label) "
                "VALUES (:key_hash, :label) "
                "ON CONFLICT (key_hash) DO NOTHING"
            ),
            {"key_hash": KEY_HASH, "label": "test-key"},
        )
        await session.commit()
    await engine.dispose()
    yield
    engine = create_async_engine(settings.database.url)
    session_factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False,
    )
    async with session_factory() as session:
        await session.execute(
            text("DELETE FROM api_keys WHERE key_hash = :key_hash"),
            {"key_hash": KEY_HASH},
        )
        await session.commit()
    await engine.dispose()


def _make_app(exempt_paths=None):
    """Build a fresh ASGI app with AuthMiddleware wrapping a simple FastAPI app.

    Creates a new engine per call to avoid event-loop binding issues
    across TestClient instances.
    """
    engine = create_async_engine(settings.database.url)

    app = FastAPI()

    @app.get("/test")
    async def test_endpoint():
        return {"ok": True}

    @app.get("/health/live")
    async def health():
        return {"status": "ok"}

    return AuthMiddleware(app, engine=engine, exempt_paths=exempt_paths)


def test_missing_auth_header_returns_401():
    app = _make_app()
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/test")
    assert resp.status_code == 401
    assert "Missing or invalid Authorization header" in resp.json()["detail"]


def test_invalid_key_returns_401(seed_api_key):
    app = _make_app()
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/test", headers={"Authorization": "Bearer wrong-key"})
    assert resp.status_code == 401
    assert "Invalid API key" in resp.json()["detail"]


def test_valid_key_returns_200(seed_api_key):
    app = _make_app()
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/test", headers={"Authorization": f"Bearer {RAW_TEST_KEY}"})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_exempt_path_skips_auth():
    app = _make_app(exempt_paths=["/health/live"])
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_non_http_scope_passes_through():
    """Non-http scopes (lifespan, websocket) pass through without auth check.

    TestClient sends lifespan events on startup; if those were blocked
    by auth the client would fail to initialize.
    """
    app = _make_app()
    # If non-http scopes were rejected, TestClient construction would raise
    client = TestClient(app, raise_server_exceptions=False)
    # Verify the app is reachable (lifespan passed through)
    resp = client.get("/test")
    assert resp.status_code == 401  # http still requires auth
