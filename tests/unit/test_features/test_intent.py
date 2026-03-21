"""Unit tests for intent feature definitions."""

from collections import defaultdict
from datetime import datetime, timezone

import src.services.features.definitions.intent  # noqa: F401 — registers features
from src.services.features.registry import registry
from tests.unit.test_features.conftest import make_test_event, make_test_lead

AS_OF = datetime(2024, 1, 31, tzinfo=timezone.utc)
LEAD = make_test_lead()


def _bucket(events):
    """Build events_by_type dict from a flat event list."""
    by_type = defaultdict(list)
    for e in events:
        by_type[e.event_type].append(e)
    by_type["_all"] = events
    return dict(by_type)


class TestViewedPricing:
    def test_returns_true_with_matching_event(self):
        events = [make_test_event(event_type="page_view", event_name="Pricing")]
        assert registry.get_function("viewed_pricing")(LEAD, _bucket(events), AS_OF) is True

    def test_returns_false_without_matching_event(self):
        events = [make_test_event(event_type="page_view", event_name="Home")]
        assert registry.get_function("viewed_pricing")(LEAD, _bucket(events), AS_OF) is False

    def test_returns_false_wrong_event_type(self):
        events = [make_test_event(event_type="form_submission", event_name="Pricing")]
        assert registry.get_function("viewed_pricing")(LEAD, _bucket(events), AS_OF) is False

    def test_returns_false_empty_events(self):
        assert registry.get_function("viewed_pricing")(LEAD, {"_all": []}, AS_OF) is False


class TestRequestedDemo:
    def test_returns_true_with_matching_event(self):
        events = [make_test_event(event_type="form_submission", event_name="Demo Request")]
        assert registry.get_function("requested_demo")(LEAD, _bucket(events), AS_OF) is True

    def test_returns_false_without_matching_event(self):
        events = [make_test_event(event_type="form_submission", event_name="Contact Us")]
        assert registry.get_function("requested_demo")(LEAD, _bucket(events), AS_OF) is False

    def test_returns_false_wrong_event_type(self):
        events = [make_test_event(event_type="page_view", event_name="Demo Request")]
        assert registry.get_function("requested_demo")(LEAD, _bucket(events), AS_OF) is False

    def test_returns_false_empty_events(self):
        assert registry.get_function("requested_demo")(LEAD, {"_all": []}, AS_OF) is False


class TestDownloadedContent:
    def test_returns_true_with_matching_event(self):
        events = [make_test_event(event_type="form_submission", event_name="Content Download")]
        assert registry.get_function("downloaded_content")(LEAD, _bucket(events), AS_OF) is True

    def test_returns_false_without_matching_event(self):
        events = [make_test_event(event_type="form_submission", event_name="Demo Request")]
        assert registry.get_function("downloaded_content")(LEAD, _bucket(events), AS_OF) is False

    def test_returns_false_wrong_event_type(self):
        events = [make_test_event(event_type="page_view", event_name="Content Download")]
        assert registry.get_function("downloaded_content")(LEAD, _bucket(events), AS_OF) is False

    def test_returns_false_empty_events(self):
        assert registry.get_function("downloaded_content")(LEAD, {"_all": []}, AS_OF) is False


class TestVisitedCompetitorComparison:
    def test_returns_true_with_matching_event(self):
        events = [make_test_event(event_type="page_view", event_name="Competitor Comparison")]
        assert registry.get_function("visited_competitor_comparison")(LEAD, _bucket(events), AS_OF) is True

    def test_returns_false_without_matching_event(self):
        events = [make_test_event(event_type="page_view", event_name="Pricing")]
        assert registry.get_function("visited_competitor_comparison")(LEAD, _bucket(events), AS_OF) is False

    def test_returns_false_wrong_event_type(self):
        events = [make_test_event(event_type="form_submission", event_name="Competitor Comparison")]
        assert registry.get_function("visited_competitor_comparison")(LEAD, _bucket(events), AS_OF) is False

    def test_returns_false_empty_events(self):
        assert registry.get_function("visited_competitor_comparison")(LEAD, {"_all": []}, AS_OF) is False
