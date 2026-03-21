"""Unit tests for recency feature functions."""

from datetime import datetime, timezone, timedelta

from src.services.features.definitions.recency import (
    days_since_last_visit,
    days_since_last_email_open,
    days_since_first_touch,
)
from tests.unit.test_features.conftest import make_test_lead, make_test_event


class TestDaysSinceLastVisit:
    def test_with_page_views(self):
        as_of = datetime(2026, 3, 15, tzinfo=timezone.utc)
        events = [
            make_test_event(event_type="page_view", occurred_at=as_of - timedelta(days=3)),
            make_test_event(event_type="page_view", occurred_at=as_of - timedelta(days=10)),
        ]
        events_by_type = {"page_view": events, "_all": events}
        lead = make_test_lead()
        assert days_since_last_visit(lead, events_by_type, as_of) == 3

    def test_no_page_views_returns_default(self):
        as_of = datetime(2026, 3, 15, tzinfo=timezone.utc)
        events = [
            make_test_event(event_type="email_open", occurred_at=as_of - timedelta(days=1)),
        ]
        events_by_type = {"email_open": events, "_all": events}
        lead = make_test_lead()
        assert days_since_last_visit(lead, events_by_type, as_of) == 365

    def test_no_events_returns_default(self):
        as_of = datetime(2026, 3, 15, tzinfo=timezone.utc)
        lead = make_test_lead()
        events_by_type = {"_all": []}
        assert days_since_last_visit(lead, events_by_type, as_of) == 365


class TestDaysSinceLastEmailOpen:
    def test_with_email_opens(self):
        as_of = datetime(2026, 3, 15, tzinfo=timezone.utc)
        events = [
            make_test_event(event_type="email_open", occurred_at=as_of - timedelta(days=5)),
            make_test_event(event_type="email_open", occurred_at=as_of - timedelta(days=20)),
        ]
        events_by_type = {"email_open": events, "_all": events}
        lead = make_test_lead()
        assert days_since_last_email_open(lead, events_by_type, as_of) == 5

    def test_no_email_opens_returns_default(self):
        as_of = datetime(2026, 3, 15, tzinfo=timezone.utc)
        lead = make_test_lead()
        events_by_type = {"_all": []}
        assert days_since_last_email_open(lead, events_by_type, as_of) == 365


class TestDaysSinceFirstTouch:
    def test_with_events(self):
        as_of = datetime(2026, 3, 15, tzinfo=timezone.utc)
        pv = [make_test_event(event_type="page_view", occurred_at=as_of - timedelta(days=30))]
        eo = [make_test_event(event_type="email_open", occurred_at=as_of - timedelta(days=10))]
        events_by_type = {"page_view": pv, "email_open": eo, "_all": pv + eo}
        lead = make_test_lead()
        assert days_since_first_touch(lead, events_by_type, as_of) == 30

    def test_no_events_returns_default(self):
        as_of = datetime(2026, 3, 15, tzinfo=timezone.utc)
        lead = make_test_lead()
        events_by_type = {"_all": []}
        assert days_since_first_touch(lead, events_by_type, as_of) == 0
