import pytest
from src.services.crm.mock import MockCRMClient
from src.services.crm.errors import CRMWritebackError


@pytest.fixture
def mock_client():
    return MockCRMClient()


async def test_push_score_records_call(mock_client):
    await mock_client.push_score("ext-1", 0.85, "A", [{"feature": "x", "impact": 0.1, "value": 1}], "v1.0")
    assert len(mock_client.push_score_calls) == 1
    call = mock_client.push_score_calls[0]
    assert call["external_id"] == "ext-1"
    assert call["score"] == 0.85
    assert call["bucket"] == "A"


async def test_push_score_raises_configured_error():
    client = MockCRMClient(push_score_error=CRMWritebackError("fail"))
    with pytest.raises(CRMWritebackError):
        await client.push_score("ext-1", 0.5, "B", [], "v1.0")


async def test_fetch_contact_returns_configured_data():
    data = {"email": "test@example.com", "job_title": "CTO"}
    client = MockCRMClient(contact_data=data)
    result = await client.fetch_contact("ext-1")
    assert result == data


async def test_validate_webhook_returns_true_by_default(mock_client):
    result = await mock_client.validate_webhook({}, b"body")
    assert result is True


async def test_parse_webhook_event_returns_empty_by_default(mock_client):
    events = await mock_client.parse_webhook_event({})
    assert events == []
