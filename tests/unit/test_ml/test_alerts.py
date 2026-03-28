"""Tests for webhook alerting.

send_alert is a thin httpx wrapper — unit tests verify the contract
(skip when no URL, construct payload correctly, handle errors).
HTTP behavior is validated by the integration test suite.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from src.ml.alerts import send_alert


@pytest.mark.asyncio
async def test_send_alert_skips_when_no_url():
    result = await send_alert("retrain.success", {"version": "v1.0"}, webhook_url=None)
    assert result is False


@pytest.mark.asyncio
async def test_send_alert_constructs_payload_correctly():
    """Verify the payload structure sent to the webhook URL."""
    captured_request = {}

    async def fake_post(url, *, json=None, **kwargs):
        captured_request["url"] = url
        captured_request["json"] = json
        resp = AsyncMock()
        resp.status_code = 200
        return resp

    fake_client = AsyncMock()
    fake_client.post = fake_post
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=False)

    with patch("src.ml.alerts.httpx.AsyncClient", return_value=fake_client):
        result = await send_alert(
            "retrain.success",
            {"version": "v1.0", "metrics": {"auc_roc": 0.91}},
            webhook_url="https://hooks.example.com/test",
        )

    assert result is True
    assert captured_request["url"] == "https://hooks.example.com/test"

    payload = captured_request["json"]
    assert payload["event_type"] == "retrain.success"
    assert payload["data"]["version"] == "v1.0"
    assert payload["data"]["metrics"]["auc_roc"] == 0.91
    assert "timestamp" in payload
    # Verify timestamp is valid ISO format
    from datetime import datetime
    datetime.fromisoformat(payload["timestamp"])


@pytest.mark.asyncio
async def test_send_alert_returns_false_on_network_error():
    """Network errors should be caught and return False, not raise."""
    fake_client = AsyncMock()
    fake_client.post.side_effect = ConnectionError("Connection refused")
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=False)

    with patch("src.ml.alerts.httpx.AsyncClient", return_value=fake_client):
        result = await send_alert(
            "retrain.failed",
            {"error": "boom"},
            webhook_url="https://hooks.example.com/test",
        )
    assert result is False


@pytest.mark.asyncio
async def test_send_alert_returns_true_even_on_http_error_status():
    """Non-2xx HTTP responses still return True (fire-and-forget, delivery succeeded)."""
    fake_client = AsyncMock()
    resp = AsyncMock()
    resp.status_code = 500
    fake_client.post.return_value = resp
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=False)

    with patch("src.ml.alerts.httpx.AsyncClient", return_value=fake_client):
        result = await send_alert(
            "retrain.blocked",
            {"reason": "auc dropped"},
            webhook_url="https://hooks.example.com/test",
        )
    # The implementation returns True after any successful POST, regardless of status code
    assert result is True
