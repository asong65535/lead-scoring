import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.crm.base import WebhookEvent


@pytest.fixture
def rescore_triggers():
    return {
        "property_changes": ["jobtitle", "lifecyclestage"],
        "engagement_types": ["EMAIL_OPEN", "FORM_SUBMISSION"],
    }


class TestShouldRescore:
    """Test the filtering logic that decides whether a webhook event triggers rescoring."""

    def test_matching_property_change_returns_true(self, rescore_triggers):
        from src.api.routes.webhooks import _should_rescore

        event = WebhookEvent(
            external_id="123",
            change_type="property_change",
            changed_fields=["jobtitle"],
            raw={},
        )
        assert _should_rescore(event, rescore_triggers) is True

    def test_non_matching_property_change_returns_false(self, rescore_triggers):
        from src.api.routes.webhooks import _should_rescore

        event = WebhookEvent(
            external_id="123",
            change_type="property_change",
            changed_fields=["phone"],
            raw={},
        )
        assert _should_rescore(event, rescore_triggers) is False

    def test_engagement_event_returns_true(self, rescore_triggers):
        from src.api.routes.webhooks import _should_rescore

        event = WebhookEvent(
            external_id="123",
            change_type="engagement",
            changed_fields=[],
            raw={"subscriptionType": "contact.EMAIL_OPEN"},
        )
        assert _should_rescore(event, rescore_triggers) is True


class TestDebounce:
    """Test the debounce logic that skips rescoring if a lead was recently scored."""

    async def test_recently_scored_lead_is_debounced(self):
        from src.api.routes.webhooks import _is_debounced

        session = AsyncMock()
        result_mock = MagicMock()
        recent_time = datetime.now(timezone.utc) - timedelta(seconds=10)
        result_mock.scalar_one_or_none.return_value = recent_time
        session.execute = AsyncMock(return_value=result_mock)

        lead_id = uuid.uuid4()
        assert await _is_debounced(session, lead_id, debounce_seconds=60) is True

    async def test_old_score_is_not_debounced(self):
        from src.api.routes.webhooks import _is_debounced

        session = AsyncMock()
        result_mock = MagicMock()
        old_time = datetime.now(timezone.utc) - timedelta(seconds=120)
        result_mock.scalar_one_or_none.return_value = old_time
        session.execute = AsyncMock(return_value=result_mock)

        lead_id = uuid.uuid4()
        assert await _is_debounced(session, lead_id, debounce_seconds=60) is False

    async def test_never_scored_is_not_debounced(self):
        from src.api.routes.webhooks import _is_debounced

        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result_mock)

        lead_id = uuid.uuid4()
        assert await _is_debounced(session, lead_id, debounce_seconds=60) is False
