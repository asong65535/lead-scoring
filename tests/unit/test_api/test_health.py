"""Tests for health endpoints with real checks wired."""

from unittest.mock import MagicMock, AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.health import router


def _make_app(model=None, model_version="v1.0"):
    app = FastAPI()
    app.state.settings = MagicMock()
    app.state.settings.app_version = "0.1.0"
    app.state.settings.environment = "test"
    app.state.model = model
    app.state.model_version = model_version
    app.include_router(router)
    return app


class TestHealthEndpoint:
    @patch("src.api.routes.health._check_database")
    def test_healthy_when_all_ok(self, mock_db):
        mock_db.return_value = {"healthy": True}
        client = TestClient(_make_app(model=MagicMock()))
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

    @patch("src.api.routes.health._check_database")
    def test_degraded_when_model_not_loaded(self, mock_db):
        mock_db.return_value = {"healthy": True}
        client = TestClient(_make_app(model=None))
        resp = client.get("/health")
        data = resp.json()
        assert data["status"] == "degraded"
        assert data["checks"]["model_loaded"]["loaded"] is False


class TestReadinessEndpoint:
    @patch("src.api.routes.health._check_database_connection")
    def test_not_ready_when_model_missing(self, mock_db):
        mock_db.return_value = True
        client = TestClient(_make_app(model=None))
        resp = client.get("/health/ready")
        data = resp.json()
        assert data["ready"] is False
        assert data["checks"]["model"] is False

    @patch("src.api.routes.health._check_database_connection")
    def test_ready_when_all_ok(self, mock_db):
        mock_db.return_value = True
        client = TestClient(_make_app(model=MagicMock()))
        resp = client.get("/health/ready")
        assert resp.json()["ready"] is True


class TestLivenessEndpoint:
    def test_always_returns_alive(self):
        client = TestClient(_make_app())
        resp = client.get("/health/live")
        assert resp.status_code == 200
        assert resp.json()["status"] == "alive"
