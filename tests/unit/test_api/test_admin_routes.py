"""Tests for admin route handlers."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.admin import router
from src.models.database import get_session


def _make_app(mock_session=None):
    app = FastAPI()
    app.state.model = MagicMock()
    app.state.model_version = "v1.0"
    app.include_router(router, prefix="/admin")

    if mock_session:
        app.dependency_overrides[get_session] = lambda: mock_session

    return app


class TestGetModel:
    def test_returns_model_info(self):
        mock_session = AsyncMock()
        mock_row = MagicMock()
        mock_row.version = "v1.0"
        mock_row.metrics = {"auc_roc": 0.92}
        mock_row.feature_columns = ["f1", "f2"]
        mock_row.trained_at = datetime.now(timezone.utc)
        mock_row.is_active = True

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_row
        mock_session.execute = AsyncMock(return_value=mock_result)

        client = TestClient(_make_app(mock_session))
        resp = client.get("/admin/model")

        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == "v1.0"
        assert data["is_active"] is True

    def test_404_when_no_active_model(self):
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        client = TestClient(_make_app(mock_session))
        resp = client.get("/admin/model")

        assert resp.status_code == 404
