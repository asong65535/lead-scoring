"""Tests for webhook endpoints."""

from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.dependencies import get_scoring_service
from src.api.routes.webhooks import router
from src.models.database import get_session


def _make_app():
    app = FastAPI()
    app.include_router(router, prefix="/webhooks")
    app.state.crm_client = None
    app.dependency_overrides[get_session] = lambda: AsyncMock()
    app.dependency_overrides[get_scoring_service] = lambda: AsyncMock()
    return app


class TestHubSpotWebhook:
    def test_no_crm_client_returns_received(self):
        client = TestClient(_make_app())
        resp = client.post(
            "/webhooks/hubspot",
            json=[{"eventId": 1, "subscriptionType": "contact.creation"}],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "received"
        assert data["processed"] == 0


class TestSalesforceWebhook:
    def test_accepts_payload_and_returns_200(self):
        client = TestClient(_make_app())
        resp = client.post(
            "/webhooks/salesforce",
            json={"sobject": "Contact", "action": "updated"},
        )
        assert resp.status_code == 200
        assert "received" in resp.json()["status"]
