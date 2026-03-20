"""Unit tests for engagement feature definitions."""

from datetime import datetime, timedelta

import pytest

from tests.unit.test_features.conftest import make_test_event, make_test_lead
from src.services.features.definitions.engagement import (
    engagement_velocity_7d,
    is_engagement_increasing,
)

AS_OF = datetime(2026, 3, 20, 12, 0, 0)
MIDPOINT = AS_OF - timedelta(days=3.5)
WINDOW_START = AS_OF - timedelta(days=7)


def _recent_event(event_type="page_view"):
    """Event in the recent half (between midpoint and as_of_date)."""
    occurred_at = MIDPOINT + timedelta(hours=1)
    return make_test_event(event_type=event_type, occurred_at=occurred_at)


def _older_event(event_type="page_view"):
    """Event in the older half (between window_start and midpoint)."""
    occurred_at = WINDOW_START + timedelta(hours=1)
    return make_test_event(event_type=event_type, occurred_at=occurred_at)


@pytest.fixture
def lead():
    return make_test_lead()


class TestEngagementVelocity7d:
    def test_accelerating(self, lead):
        events = [_recent_event(), _recent_event(), _recent_event(), _older_event()]
        assert engagement_velocity_7d(lead, events, AS_OF) == 2

    def test_decelerating(self, lead):
        events = [_recent_event(), _older_event(), _older_event(), _older_event()]
        assert engagement_velocity_7d(lead, events, AS_OF) == -2

    def test_email_unsubscribe_subtracts_one(self, lead):
        events = [
            _recent_event("email_unsubscribe"),
            _recent_event("page_view"),
            _older_event("page_view"),
        ]
        # recent = -1 + 1 = 0, older = 1 → velocity = -1
        assert engagement_velocity_7d(lead, events, AS_OF) == -1

    def test_no_events_in_window(self, lead):
        outside = make_test_event(
            event_type="page_view",
            occurred_at=AS_OF - timedelta(days=30),
        )
        assert engagement_velocity_7d(lead, [outside], AS_OF) == 0

    def test_empty_events(self, lead):
        assert engagement_velocity_7d(lead, [], AS_OF) == 0


class TestIsEngagementIncreasing:
    def test_true_when_velocity_positive(self, lead):
        events = [_recent_event(), _recent_event(), _older_event()]
        assert is_engagement_increasing(lead, events, AS_OF) is True

    def test_false_when_velocity_zero(self, lead):
        events = [_recent_event(), _older_event()]
        assert is_engagement_increasing(lead, events, AS_OF) is False

    def test_false_when_velocity_negative(self, lead):
        events = [_recent_event(), _older_event(), _older_event()]
        assert is_engagement_increasing(lead, events, AS_OF) is False
