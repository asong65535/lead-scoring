import hashlib
import hmac
import json
import time

import httpx
import pytest
from unittest.mock import AsyncMock

from src.services.crm.hubspot import HubSpotClient
from src.services.crm.errors import (
    CRMContactNotFoundError,
    CRMRateLimitError,
    CRMWritebackError,
)


@pytest.fixture
def field_mappings():
    return {
        "output_fields": {
            "score": "lead_score",
            "bucket": "lead_score_bucket",
            "top_factors": "lead_score_factors",
            "scored_at": "lead_score_updated",
            "model_version": "lead_score_model_version",
        },
        "contact_fields": {
            "email": "email",
            "job_title": "jobtitle",
        },
    }


@pytest.fixture
def client(field_mappings):
    return HubSpotClient(
        access_token="test-token",
        client_secret="test-secret",
        field_mappings=field_mappings,
    )


class TestPushScore:
    async def test_push_score_sends_patch_with_mapped_fields(self, client):
        mock_response = httpx.Response(200, json={})
        client._http.request = AsyncMock(return_value=mock_response)

        await client.push_score(
            external_id="123",
            score=0.85,
            bucket="A",
            top_factors=[{"feature": "visits", "impact": 0.1, "value": 5}],
            model_version="v1.0",
        )

        client._http.request.assert_called_once()
        call_kwargs = client._http.request.call_args
        assert call_kwargs.kwargs["method"] == "PATCH"
        assert "123" in call_kwargs.kwargs["url"]
        props = call_kwargs.kwargs["json"]["properties"]
        assert props["lead_score"] == 0.85
        assert props["lead_score_bucket"] == "A"
        assert props["lead_score_model_version"] == "v1.0"

    async def test_push_score_raises_on_404(self, client):
        mock_response = httpx.Response(404, json={"message": "not found"})
        client._http.request = AsyncMock(return_value=mock_response)

        with pytest.raises(CRMContactNotFoundError):
            await client.push_score("missing-id", 0.5, "B", [], "v1.0")

    async def test_push_score_raises_on_429(self, client):
        mock_response = httpx.Response(429, json={}, headers={"Retry-After": "10"})
        client._http.request = AsyncMock(return_value=mock_response)

        with pytest.raises(CRMRateLimitError) as exc_info:
            await client.push_score("123", 0.5, "B", [], "v1.0")
        assert exc_info.value.retry_after == 10

    async def test_push_score_raises_writeback_error_on_5xx(self, client):
        mock_response = httpx.Response(500, json={"message": "internal error"})
        client._http.request = AsyncMock(return_value=mock_response)

        with pytest.raises(CRMWritebackError):
            await client.push_score("123", 0.5, "B", [], "v1.0")


class TestFetchContact:
    async def test_fetch_contact_returns_mapped_fields(self, client):
        mock_response = httpx.Response(200, json={
            "properties": {
                "email": "test@example.com",
                "jobtitle": "CTO",
            },
        })
        client._http.request = AsyncMock(return_value=mock_response)

        result = await client.fetch_contact("123")
        assert result["email"] == "test@example.com"
        assert result["job_title"] == "CTO"

    async def test_fetch_contact_raises_on_404(self, client):
        mock_response = httpx.Response(404, json={"message": "not found"})
        client._http.request = AsyncMock(return_value=mock_response)

        with pytest.raises(CRMContactNotFoundError):
            await client.fetch_contact("missing")


class TestValidateWebhook:
    def _sign(self, client_secret: str, method: str, url: str, body: bytes, timestamp: str) -> str:
        source = f"{method}{url}{body.decode()}{timestamp}"
        return hmac.new(
            client_secret.encode(), source.encode(), hashlib.sha256,
        ).hexdigest()

    async def test_valid_signature_returns_true(self, client):
        body = b'[{"objectId": 123}]'
        ts = str(int(time.time()))
        method = "POST"
        uri = "https://example.com/webhooks/hubspot"
        sig = self._sign("test-secret", method, uri, body, ts)
        headers = {
            "x-hubspot-signature-v3": sig,
            "x-hubspot-request-timestamp": ts,
        }
        assert await client.validate_webhook(headers, body, method=method, uri=uri) is True

    async def test_tampered_signature_returns_false(self, client):
        headers = {
            "x-hubspot-signature-v3": "bad-signature",
            "x-hubspot-request-timestamp": str(int(time.time())),
        }
        assert await client.validate_webhook(
            headers, b"body", method="POST", uri="https://example.com/webhooks/hubspot",
        ) is False

    async def test_expired_timestamp_returns_false(self, client):
        old_ts = str(int(time.time()) - 600)  # 10 minutes ago
        body = b"body"
        method = "POST"
        uri = "https://example.com/webhooks/hubspot"
        sig = self._sign("test-secret", method, uri, body, old_ts)
        headers = {
            "x-hubspot-signature-v3": sig,
            "x-hubspot-request-timestamp": old_ts,
        }
        assert await client.validate_webhook(headers, body, method=method, uri=uri) is False


class TestParseWebhookEvent:
    async def test_parses_property_change(self, client):
        payload = [
            {
                "objectId": 123,
                "propertyName": "jobtitle",
                "propertyValue": "CTO",
                "subscriptionType": "contact.propertyChange",
            },
        ]
        events = await client.parse_webhook_event(payload)
        assert len(events) == 1
        assert events[0].external_id == "123"
        assert events[0].change_type == "property_change"
        assert "jobtitle" in events[0].changed_fields

    async def test_parses_engagement_event(self, client):
        payload = [
            {
                "objectId": 456,
                "subscriptionType": "contact.creation",
            },
        ]
        events = await client.parse_webhook_event(payload)
        assert len(events) == 1
        assert events[0].external_id == "456"
        assert events[0].change_type == "engagement"
        assert events[0].changed_fields == []
