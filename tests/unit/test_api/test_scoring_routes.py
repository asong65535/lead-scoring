"""Tests for scoring route handlers — mocked ScoringService."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.dependencies import get_scoring_service
from src.api.exceptions import LeadNotFoundError, ModelNotLoadedError
from src.api.routes.scoring import router
from src.services.scoring import ScoreResult


def _make_app(mock_service):
    app = FastAPI()
    app.include_router(router, prefix="/score")

    from src.api.exceptions import LeadNotFoundError
    from fastapi.responses import JSONResponse

    @app.exception_handler(LeadNotFoundError)
    async def _(request, exc):
        return JSONResponse(status_code=404, content={"detail": str(exc), "lead_id": str(exc.lead_id)})

    @app.exception_handler(ModelNotLoadedError)
    async def _(request, exc):
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    app.dependency_overrides[get_scoring_service] = lambda: mock_service
    return app


def _make_score_result(lead_id=None):
    return ScoreResult(
        lead_id=lead_id or uuid4(),
        score=0.85,
        bucket="A",
        model_version="v1.0",
        top_factors=[{"feature": "total_visits", "impact": 0.3, "value": 42}],
        scored_at=datetime.now(timezone.utc),
    )


class TestScoreSingle:
    def test_returns_score(self):
        lead_id = uuid4()
        svc = AsyncMock()
        svc.score_lead.return_value = _make_score_result(lead_id)

        client = TestClient(_make_app(svc))
        resp = client.post(f"/score/{lead_id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["lead_id"] == str(lead_id)
        assert data["bucket"] == "A"

    def test_404_when_lead_not_found(self):
        lead_id = uuid4()
        svc = AsyncMock()
        svc.score_lead.side_effect = LeadNotFoundError(lead_id)

        client = TestClient(_make_app(svc))
        resp = client.post(f"/score/{lead_id}")

        assert resp.status_code == 404


class TestScoreBatch:
    def test_returns_results_and_errors(self):
        id1, id2, id_missing = uuid4(), uuid4(), uuid4()
        svc = AsyncMock()
        svc.score_leads.return_value = (
            [_make_score_result(id1), _make_score_result(id2)],
            [id_missing],
            [],  # no scoring errors
        )

        client = TestClient(_make_app(svc))
        resp = client.post("/score/batch", json={"lead_ids": [str(id1), str(id2), str(id_missing)]})

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) == 2
        assert len(data["errors"]) == 1
        assert data["errors"][0]["lead_id"] == str(id_missing)

    def test_422_when_empty_list(self):
        svc = AsyncMock()
        client = TestClient(_make_app(svc))
        resp = client.post("/score/batch", json={"lead_ids": []})
        assert resp.status_code == 422
