"""Tests for hardened model reload in admin routes."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.admin import router
from src.models.database import get_session


def _mock_registry_row(artifact_path="/tmp/model.pkl", version="v2.0"):
    row = MagicMock()
    row.artifact_path = artifact_path
    row.version = version
    row.is_active = True
    return row


def _make_app(mock_session):
    """Create a minimal FastAPI app with admin router and required state."""
    app = FastAPI()
    app.state.model = MagicMock()
    app.state.model_version = "v1.0"
    app.state.model_lock = asyncio.Lock()
    app.include_router(router, prefix="/admin")
    app.dependency_overrides[get_session] = lambda: mock_session
    return app


def _make_session_with_row(row):
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = row
    mock_session.execute = AsyncMock(return_value=mock_result)
    return mock_session


class TestReloadModelCorruptFile:
    def test_corrupt_model_returns_500_with_error_type(self):
        session = _make_session_with_row(_mock_registry_row())
        app = _make_app(session)

        with (
            patch("src.api.routes.admin.load_model", side_effect=EOFError("corrupt")),
            patch("src.api.routes.admin.Path") as mock_path_cls,
        ):
            mock_path_cls.side_effect = lambda p: mock_path_cls.return_value
            mock_path_cls.return_value.exists.return_value = True

            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post("/admin/reload-model")

        assert resp.status_code == 500
        assert "EOFError" in resp.json()["detail"]


class TestReloadModelMissingPredictProba:
    def test_model_without_predict_proba_returns_500(self):
        session = _make_session_with_row(_mock_registry_row())
        app = _make_app(session)

        bad_model = object()  # no predict_proba

        with (
            patch("src.api.routes.admin.load_model", return_value=bad_model),
            patch("src.api.routes.admin.Path") as mock_path_cls,
        ):
            mock_path_cls.side_effect = lambda p: mock_path_cls.return_value
            mock_path_cls.return_value.exists.return_value = True

            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post("/admin/reload-model")

        assert resp.status_code == 500
        assert "predict_proba" in resp.json()["detail"]


class TestReloadModelMissingPipelineStructure:
    def test_model_without_named_steps_returns_500(self):
        session = _make_session_with_row(_mock_registry_row())
        app = _make_app(session)

        # Has predict_proba but no named_steps
        bad_model = MagicMock(spec=["predict_proba"])

        with (
            patch("src.api.routes.admin.load_model", return_value=bad_model),
            patch("src.api.routes.admin.Path") as mock_path_cls,
        ):
            mock_path_cls.side_effect = lambda p: mock_path_cls.return_value
            mock_path_cls.return_value.exists.return_value = True

            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post("/admin/reload-model")

        assert resp.status_code == 500
        assert "pipeline" in resp.json()["detail"].lower()
