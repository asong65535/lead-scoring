"""Unit tests for frequency feature definitions."""

from datetime import datetime, timedelta

import pytest

from tests.unit.test_features.conftest import make_test_event, make_test_lead

AS_OF = datetime(2024, 6, 15, 12, 0, 0)


@pytest.fixture(autouse=True)
def _import_definitions():
    """Ensure frequency definitions are registered before tests run."""
    import src.services.features.definitions.frequency  # noqa: F401


def _lead():
    return make_test_lead()


# ---------------------------------------------------------------------------
# total_pageviews_7d
# ---------------------------------------------------------------------------

class TestTotalPageviews7d:
    def _compute(self, events):
        from src.services.features.registry import registry
        fn = registry.get_function("total_pageviews_7d")
        return fn(_lead(), events, AS_OF)

    def test_counts_page_views_in_window(self):
        in_window = [
            make_test_event(event_type="page_view", occurred_at=AS_OF - timedelta(days=1)),
            make_test_event(event_type="page_view", occurred_at=AS_OF - timedelta(days=6)),
        ]
        outside = [
            make_test_event(event_type="page_view", occurred_at=AS_OF - timedelta(days=8)),
        ]
        assert self._compute(in_window + outside) == 2

    def test_no_matching_events_returns_zero(self):
        assert self._compute([]) == 0

    def test_excludes_events_outside_window(self):
        events = [
            make_test_event(event_type="page_view", occurred_at=AS_OF - timedelta(days=10)),
        ]
        assert self._compute(events) == 0

    def test_excludes_non_page_view_events(self):
        events = [
            make_test_event(event_type="email_open", occurred_at=AS_OF - timedelta(days=1)),
        ]
        assert self._compute(events) == 0

    def test_window_lower_bound_is_inclusive(self):
        boundary = [
            make_test_event(event_type="page_view", occurred_at=AS_OF - timedelta(days=7)),
        ]
        assert self._compute(boundary) == 1

    def test_as_of_date_upper_bound_is_exclusive(self):
        at_boundary = [
            make_test_event(event_type="page_view", occurred_at=AS_OF),
        ]
        assert self._compute(at_boundary) == 0


# ---------------------------------------------------------------------------
# total_pageviews_30d
# ---------------------------------------------------------------------------

class TestTotalPageviews30d:
    def _compute(self, events):
        from src.services.features.registry import registry
        fn = registry.get_function("total_pageviews_30d")
        return fn(_lead(), events, AS_OF)

    def test_counts_page_views_in_window(self):
        in_window = [
            make_test_event(event_type="page_view", occurred_at=AS_OF - timedelta(days=1)),
            make_test_event(event_type="page_view", occurred_at=AS_OF - timedelta(days=15)),
            make_test_event(event_type="page_view", occurred_at=AS_OF - timedelta(days=29)),
        ]
        outside = [
            make_test_event(event_type="page_view", occurred_at=AS_OF - timedelta(days=31)),
        ]
        assert self._compute(in_window + outside) == 3

    def test_no_matching_events_returns_zero(self):
        assert self._compute([]) == 0

    def test_excludes_events_outside_window(self):
        events = [
            make_test_event(event_type="page_view", occurred_at=AS_OF - timedelta(days=45)),
        ]
        assert self._compute(events) == 0

    def test_window_lower_bound_is_inclusive(self):
        boundary = [
            make_test_event(event_type="page_view", occurred_at=AS_OF - timedelta(days=30)),
        ]
        assert self._compute(boundary) == 1


# ---------------------------------------------------------------------------
# total_sessions (LIFETIME feature)
# ---------------------------------------------------------------------------

class TestTotalSessions:
    def _compute(self, events):
        from src.services.features.registry import registry
        fn = registry.get_function("total_sessions")
        return fn(_lead(), events, AS_OF)

    def test_counts_distinct_session_ids(self):
        events = [
            make_test_event(event_type="page_view", occurred_at=AS_OF - timedelta(days=1), properties={"session_id": "s1"}),
            make_test_event(event_type="page_view", occurred_at=AS_OF - timedelta(days=2), properties={"session_id": "s2"}),
            make_test_event(event_type="page_view", occurred_at=AS_OF - timedelta(days=3), properties={"session_id": "s1"}),
        ]
        assert self._compute(events) == 2

    def test_no_events_returns_zero(self):
        assert self._compute([]) == 0

    def test_is_lifetime_not_windowed(self):
        """Events well outside any window still count for total_sessions."""
        events = [
            make_test_event(event_type="page_view", occurred_at=AS_OF - timedelta(days=365), properties={"session_id": "old-session"}),
            make_test_event(event_type="page_view", occurred_at=AS_OF - timedelta(days=1), properties={"session_id": "recent-session"}),
        ]
        assert self._compute(events) == 2

    def test_skips_events_without_session_id(self):
        events = [
            make_test_event(event_type="page_view", occurred_at=AS_OF - timedelta(days=1), properties={}),
        ]
        assert self._compute(events) == 0

    def test_skips_events_without_properties(self):
        events = [
            make_test_event(event_type="page_view", occurred_at=AS_OF - timedelta(days=1), properties=None),
        ]
        assert self._compute(events) == 0

    def test_ignores_non_page_view_events(self):
        events = [
            make_test_event(event_type="email_open", occurred_at=AS_OF - timedelta(days=1), properties={"session_id": "s1"}),
        ]
        assert self._compute(events) == 0


# ---------------------------------------------------------------------------
# emails_opened_30d
# ---------------------------------------------------------------------------

class TestEmailsOpened30d:
    def _compute(self, events):
        from src.services.features.registry import registry
        fn = registry.get_function("emails_opened_30d")
        return fn(_lead(), events, AS_OF)

    def test_counts_email_opens_in_window(self):
        in_window = [
            make_test_event(event_type="email_open", occurred_at=AS_OF - timedelta(days=5)),
            make_test_event(event_type="email_open", occurred_at=AS_OF - timedelta(days=20)),
        ]
        outside = [
            make_test_event(event_type="email_open", occurred_at=AS_OF - timedelta(days=35)),
        ]
        assert self._compute(in_window + outside) == 2

    def test_no_matching_events_returns_zero(self):
        assert self._compute([]) == 0

    def test_excludes_events_outside_window(self):
        events = [
            make_test_event(event_type="email_open", occurred_at=AS_OF - timedelta(days=40)),
        ]
        assert self._compute(events) == 0

    def test_excludes_non_email_open_events(self):
        events = [
            make_test_event(event_type="page_view", occurred_at=AS_OF - timedelta(days=1)),
            make_test_event(event_type="email_click", occurred_at=AS_OF - timedelta(days=1)),
        ]
        assert self._compute(events) == 0


# ---------------------------------------------------------------------------
# emails_clicked_30d
# ---------------------------------------------------------------------------

class TestEmailsClicked30d:
    def _compute(self, events):
        from src.services.features.registry import registry
        fn = registry.get_function("emails_clicked_30d")
        return fn(_lead(), events, AS_OF)

    def test_counts_email_clicks_in_window(self):
        in_window = [
            make_test_event(event_type="email_click", occurred_at=AS_OF - timedelta(days=3)),
            make_test_event(event_type="email_click", occurred_at=AS_OF - timedelta(days=28)),
        ]
        outside = [
            make_test_event(event_type="email_click", occurred_at=AS_OF - timedelta(days=31)),
        ]
        assert self._compute(in_window + outside) == 2

    def test_no_matching_events_returns_zero(self):
        assert self._compute([]) == 0

    def test_excludes_events_outside_window(self):
        events = [
            make_test_event(event_type="email_click", occurred_at=AS_OF - timedelta(days=60)),
        ]
        assert self._compute(events) == 0

    def test_excludes_non_email_click_events(self):
        events = [
            make_test_event(event_type="email_open", occurred_at=AS_OF - timedelta(days=1)),
            make_test_event(event_type="page_view", occurred_at=AS_OF - timedelta(days=1)),
        ]
        assert self._compute(events) == 0
