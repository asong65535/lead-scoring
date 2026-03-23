"""Tests for webhook endpoints.

Covers: no-CRM-client path, invalid signature (401), invalid JSON (400),
and the full rescore flow with a configured MockCRMClient.
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.dependencies import get_scoring_service
from src.api.routes.webhooks import router
from src.models.database import get_session
from src.services.crm.base import WebhookEvent
from src.services.crm.mock import MockCRMClient


def _make_app(crm_client=None, scoring_service=None):
    app = FastAPI()
    app.include_router(router, prefix="/webhooks")
    app.state.crm_client = crm_client
    app.dependency_overrides[get_session] = lambda: AsyncMock()
    if scoring_service is not None:
        app.dependency_overrides[get_scoring_service] = lambda: scoring_service
    else:
        app.dependency_overrides[get_scoring_service] = lambda: AsyncMock()
    return app


class TestHubSpotWebhookNoCRM:
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


class TestHubSpotWebhookSignatureValidation:
    def test_invalid_signature_returns_401(self):
        crm = MockCRMClient(webhook_valid=False)
        client = TestClient(_make_app(crm_client=crm))
        resp = client.post(
            "/webhooks/hubspot",
            json=[{"eventId": 1, "subscriptionType": "contact.creation"}],
        )
        assert resp.status_code == 401
        assert "signature" in resp.json()["detail"].lower()


class TestHubSpotWebhookBadPayload:
    def test_invalid_json_returns_400(self):
        crm = MockCRMClient(webhook_valid=True)
        client = TestClient(_make_app(crm_client=crm))
        resp = client.post(
            "/webhooks/hubspot",
            content=b"this is not json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 400
        assert "json" in resp.json()["detail"].lower()


class TestHubSpotWebhookRescoreFlow:
    def test_matching_event_triggers_rescore(self):
        """Webhook with matching trigger should call score_lead on the found lead."""
        lead_id = uuid.uuid4()
        external_id = "hs-42"

        # CRM client that returns a rescore-eligible event
        event = WebhookEvent(
            external_id=external_id,
            change_type="property_change",
            changed_fields=["jobtitle"],
            raw={},
        )
        crm = MockCRMClient(webhook_valid=True, webhook_events=[event])

        scoring_service = AsyncMock()
        scoring_service.score_lead = AsyncMock()

        app = _make_app(crm_client=crm, scoring_service=scoring_service)

        # Mock lead lookup and debounce check
        mock_lead = MagicMock()
        mock_lead.id = lead_id
        mock_lead.external_id = external_id

        mock_session = AsyncMock()

        # First execute: lead lookup → returns lead
        lead_result = MagicMock()
        lead_result.scalar_one_or_none.return_value = mock_lead

        # Second execute: debounce check → not debounced (no recent prediction)
        debounce_result = MagicMock()
        debounce_result.scalar_one_or_none.return_value = None

        mock_session.execute = AsyncMock(side_effect=[lead_result, debounce_result])

        app.dependency_overrides[get_session] = lambda: mock_session

        # Patch settings to include jobtitle in rescore triggers
        mock_settings = MagicMock()
        mock_settings.crm_mappings = {
            "hubspot": {
                "rescore_triggers": {
                    "property_changes": ["jobtitle", "lifecyclestage"],
                    "engagement_types": ["EMAIL_OPEN"],
                },
            },
        }
        mock_settings.crm.rescore_debounce_seconds = 60

        with patch("src.api.routes.webhooks.get_settings", return_value=mock_settings):
            client = TestClient(app)
            resp = client.post(
                "/webhooks/hubspot",
                json=[{"objectId": 42, "subscriptionType": "contact.propertyChange", "propertyName": "jobtitle"}],
            )

        assert resp.status_code == 200
        assert resp.json()["processed"] == 1
        scoring_service.score_lead.assert_awaited_once_with(lead_id)
        # Lead lookup + debounce check = 2 queries
        assert mock_session.execute.await_count == 2

    def test_debounced_lead_is_skipped(self):
        """Webhook for a recently-scored lead should not trigger rescore."""
        lead_id = uuid.uuid4()
        external_id = "hs-55"

        event = WebhookEvent(
            external_id=external_id,
            change_type="property_change",
            changed_fields=["jobtitle"],
            raw={},
        )
        crm = MockCRMClient(webhook_valid=True, webhook_events=[event])
        scoring_service = AsyncMock()

        app = _make_app(crm_client=crm, scoring_service=scoring_service)

        mock_lead = MagicMock()
        mock_lead.id = lead_id
        mock_lead.external_id = external_id

        mock_session = AsyncMock()

        lead_result = MagicMock()
        lead_result.scalar_one_or_none.return_value = mock_lead

        # Debounce check → recently scored (10 seconds ago)
        from datetime import datetime, timedelta, timezone
        debounce_result = MagicMock()
        debounce_result.scalar_one_or_none.return_value = datetime.now(timezone.utc) - timedelta(seconds=10)

        mock_session.execute = AsyncMock(side_effect=[lead_result, debounce_result])
        app.dependency_overrides[get_session] = lambda: mock_session

        mock_settings = MagicMock()
        mock_settings.crm_mappings = {
            "hubspot": {
                "rescore_triggers": {
                    "property_changes": ["jobtitle"],
                    "engagement_types": [],
                },
            },
        }
        mock_settings.crm.rescore_debounce_seconds = 60

        with patch("src.api.routes.webhooks.get_settings", return_value=mock_settings):
            client = TestClient(app)
            resp = client.post(
                "/webhooks/hubspot",
                json=[{"objectId": 55, "subscriptionType": "contact.propertyChange", "propertyName": "jobtitle"}],
            )

        assert resp.status_code == 200
        assert resp.json()["processed"] == 0
        scoring_service.score_lead.assert_not_awaited()

    def test_non_matching_event_is_filtered_out(self):
        """Webhook event that doesn't match rescore_triggers should not trigger scoring."""
        event = WebhookEvent(
            external_id="hs-99",
            change_type="property_change",
            changed_fields=["phone"],  # not in triggers
            raw={},
        )
        crm = MockCRMClient(webhook_valid=True, webhook_events=[event])
        scoring_service = AsyncMock()

        app = _make_app(crm_client=crm, scoring_service=scoring_service)

        mock_settings = MagicMock()
        mock_settings.crm_mappings = {
            "hubspot": {
                "rescore_triggers": {
                    "property_changes": ["jobtitle"],
                    "engagement_types": [],
                },
            },
        }
        mock_settings.crm.rescore_debounce_seconds = 60

        with patch("src.api.routes.webhooks.get_settings", return_value=mock_settings):
            client = TestClient(app)
            resp = client.post(
                "/webhooks/hubspot",
                json=[{"objectId": 99, "subscriptionType": "contact.propertyChange", "propertyName": "phone"}],
            )

        assert resp.status_code == 200
        assert resp.json()["processed"] == 0
        scoring_service.score_lead.assert_not_awaited()


class TestSalesforceWebhook:
    def test_accepts_payload_and_returns_200(self):
        client = TestClient(_make_app())
        resp = client.post(
            "/webhooks/salesforce",
            json={"sobject": "Contact", "action": "updated"},
        )
        assert resp.status_code == 200
        assert "received" in resp.json()["status"]
