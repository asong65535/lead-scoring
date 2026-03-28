"""Tests for webhook alerting."""

from unittest.mock import AsyncMock, patch

import pytest

from src.ml.alerts import send_alert


@pytest.mark.asyncio
async def test_send_alert_skips_when_no_url():
    result = await send_alert("retrain.success", {"version": "v1.0"}, webhook_url=None)
    assert result is False


@pytest.mark.asyncio
async def test_send_alert_posts_to_url():
    with patch("src.ml.alerts.httpx.AsyncClient") as MockClient:
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = mock_response
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_client_instance

        result = await send_alert(
            "retrain.success",
            {"version": "v1.0"},
            webhook_url="https://hooks.example.com/test",
        )
        assert result is True
        mock_client_instance.post.assert_called_once()
        call_args = mock_client_instance.post.call_args
        assert call_args[0][0] == "https://hooks.example.com/test"
        payload = call_args[1]["json"]
        assert payload["event_type"] == "retrain.success"
        assert payload["data"]["version"] == "v1.0"
        assert "timestamp" in payload


@pytest.mark.asyncio
async def test_send_alert_returns_false_on_http_error():
    with patch("src.ml.alerts.httpx.AsyncClient") as MockClient:
        mock_client_instance = AsyncMock()
        mock_client_instance.post.side_effect = Exception("Connection refused")
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_client_instance

        result = await send_alert(
            "retrain.failed",
            {"error": "boom"},
            webhook_url="https://hooks.example.com/test",
        )
        assert result is False
