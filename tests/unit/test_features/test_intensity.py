"""Unit tests for intensity feature definitions."""

from datetime import datetime, timezone

import pytest

import src.services.features.definitions.intensity  # noqa: F401 — registers features
from src.services.features.registry import registry
from tests.unit.test_features.conftest import make_test_event, make_test_lead

AS_OF = datetime(2024, 1, 31, tzinfo=timezone.utc)
LEAD = make_test_lead()


def ts(offset_seconds: int):
    from datetime import timedelta
    return datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=offset_seconds)


# ---------------------------------------------------------------------------
# avg_pages_per_session
# ---------------------------------------------------------------------------

class TestAvgPagesPerSession:
    def test_groups_by_session_and_averages(self):
        events = [
            make_test_event(event_type="page_view", properties={"session_id": "A"}),
            make_test_event(event_type="page_view", properties={"session_id": "A"}),
            make_test_event(event_type="page_view", properties={"session_id": "A"}),
            make_test_event(event_type="page_view", properties={"session_id": "B"}),
        ]
        result = registry.get_function("avg_pages_per_session")(LEAD, events, AS_OF)
        assert result == 2.0

    def test_no_page_views_returns_zero(self):
        events = [
            make_test_event(event_type="form_submit", properties={"session_id": "A"}),
        ]
        result = registry.get_function("avg_pages_per_session")(LEAD, events, AS_OF)
        assert result == 0

    def test_empty_events_returns_zero(self):
        result = registry.get_function("avg_pages_per_session")(LEAD, [], AS_OF)
        assert result == 0

    def test_skips_events_without_session_id(self):
        events = [
            make_test_event(event_type="page_view", properties={}),
            make_test_event(event_type="page_view", properties={"session_id": "A"}),
            make_test_event(event_type="page_view", properties=None),
        ]
        result = registry.get_function("avg_pages_per_session")(LEAD, events, AS_OF)
        assert result == 1.0


# ---------------------------------------------------------------------------
# avg_session_duration_seconds
# ---------------------------------------------------------------------------

class TestAvgSessionDurationSeconds:
    def test_session_a_120s_session_b_single_page(self):
        events = [
            make_test_event(event_type="page_view", properties={"session_id": "A"}, occurred_at=ts(0)),
            make_test_event(event_type="page_view", properties={"session_id": "A"}, occurred_at=ts(120)),
            make_test_event(event_type="page_view", properties={"session_id": "B"}, occurred_at=ts(200)),
        ]
        result = registry.get_function("avg_session_duration_seconds")(LEAD, events, AS_OF)
        assert result == 60.0

    def test_no_page_views_returns_zero(self):
        result = registry.get_function("avg_session_duration_seconds")(LEAD, [], AS_OF)
        assert result == 0

    def test_single_page_session_duration_is_zero(self):
        events = [
            make_test_event(event_type="page_view", properties={"session_id": "A"}, occurred_at=ts(0)),
        ]
        result = registry.get_function("avg_session_duration_seconds")(LEAD, events, AS_OF)
        assert result == 0.0


# ---------------------------------------------------------------------------
# pricing_page_views
# ---------------------------------------------------------------------------

class TestPricingPageViews:
    def test_counts_only_pricing_views(self):
        events = [
            make_test_event(event_type="page_view", event_name="Pricing"),
            make_test_event(event_type="page_view", event_name="Pricing"),
            make_test_event(event_type="page_view", event_name="Home"),
        ]
        result = registry.get_function("pricing_page_views")(LEAD, events, AS_OF)
        assert result == 2

    def test_no_pricing_views_returns_zero(self):
        events = [
            make_test_event(event_type="page_view", event_name="Home"),
            make_test_event(event_type="form_submit", event_name="Pricing"),
        ]
        result = registry.get_function("pricing_page_views")(LEAD, events, AS_OF)
        assert result == 0

    def test_empty_events_returns_zero(self):
        result = registry.get_function("pricing_page_views")(LEAD, [], AS_OF)
        assert result == 0
