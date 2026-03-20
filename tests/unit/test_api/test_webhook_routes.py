"""Tests for webhook stub endpoints — no CRM assertions."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.webhooks import router


def _make_app():
    app = FastAPI()
    app.include_router(router, prefix="/webhooks")
    return app


class TestHubSpotWebhook:
    def test_accepts_payload_and_returns_200(self):
        client = TestClient(_make_app())
        resp = client.post(
            "/webhooks/hubspot",
            json=[{"eventId": 1, "subscriptionType": "contact.creation"}],
        )
        assert resp.status_code == 200
        assert "received" in resp.json()["status"]


class TestSalesforceWebhook:
    def test_accepts_payload_and_returns_200(self):
        client = TestClient(_make_app())
        resp = client.post(
            "/webhooks/salesforce",
            json={"sobject": "Contact", "action": "updated"},
        )
        assert resp.status_code == 200
        assert "received" in resp.json()["status"]
