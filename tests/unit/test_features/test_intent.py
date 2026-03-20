"""Unit tests for intent feature definitions."""

from datetime import datetime, timezone

import src.services.features.definitions.intent  # noqa: F401 — registers features
from src.services.features.registry import registry
from tests.unit.test_features.conftest import make_test_event, make_test_lead

AS_OF = datetime(2024, 1, 31, tzinfo=timezone.utc)
LEAD = make_test_lead()


class TestViewedPricing:
    def test_returns_true_with_matching_event(self):
        events = [make_test_event(event_type="page_view", event_name="Pricing")]
        assert registry.get_function("viewed_pricing")(LEAD, events, AS_OF) is True

    def test_returns_false_without_matching_event(self):
        events = [make_test_event(event_type="page_view", event_name="Home")]
        assert registry.get_function("viewed_pricing")(LEAD, events, AS_OF) is False

    def test_returns_false_wrong_event_type(self):
        events = [make_test_event(event_type="form_submission", event_name="Pricing")]
        assert registry.get_function("viewed_pricing")(LEAD, events, AS_OF) is False

    def test_returns_false_empty_events(self):
        assert registry.get_function("viewed_pricing")(LEAD, [], AS_OF) is False


class TestRequestedDemo:
    def test_returns_true_with_matching_event(self):
        events = [make_test_event(event_type="form_submission", event_name="Demo Request")]
        assert registry.get_function("requested_demo")(LEAD, events, AS_OF) is True

    def test_returns_false_without_matching_event(self):
        events = [make_test_event(event_type="form_submission", event_name="Contact Us")]
        assert registry.get_function("requested_demo")(LEAD, events, AS_OF) is False

    def test_returns_false_wrong_event_type(self):
        events = [make_test_event(event_type="page_view", event_name="Demo Request")]
        assert registry.get_function("requested_demo")(LEAD, events, AS_OF) is False

    def test_returns_false_empty_events(self):
        assert registry.get_function("requested_demo")(LEAD, [], AS_OF) is False


class TestDownloadedContent:
    def test_returns_true_with_matching_event(self):
        events = [make_test_event(event_type="form_submission", event_name="Content Download")]
        assert registry.get_function("downloaded_content")(LEAD, events, AS_OF) is True

    def test_returns_false_without_matching_event(self):
        events = [make_test_event(event_type="form_submission", event_name="Demo Request")]
        assert registry.get_function("downloaded_content")(LEAD, events, AS_OF) is False

    def test_returns_false_wrong_event_type(self):
        events = [make_test_event(event_type="page_view", event_name="Content Download")]
        assert registry.get_function("downloaded_content")(LEAD, events, AS_OF) is False

    def test_returns_false_empty_events(self):
        assert registry.get_function("downloaded_content")(LEAD, [], AS_OF) is False


class TestVisitedCompetitorComparison:
    def test_returns_true_with_matching_event(self):
        events = [make_test_event(event_type="page_view", event_name="Competitor Comparison")]
        assert registry.get_function("visited_competitor_comparison")(LEAD, events, AS_OF) is True

    def test_returns_false_without_matching_event(self):
        events = [make_test_event(event_type="page_view", event_name="Pricing")]
        assert registry.get_function("visited_competitor_comparison")(LEAD, events, AS_OF) is False

    def test_returns_false_wrong_event_type(self):
        events = [make_test_event(event_type="form_submission", event_name="Competitor Comparison")]
        assert registry.get_function("visited_competitor_comparison")(LEAD, events, AS_OF) is False

    def test_returns_false_empty_events(self):
        assert registry.get_function("visited_competitor_comparison")(LEAD, [], AS_OF) is False
