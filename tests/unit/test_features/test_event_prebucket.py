"""Unit tests for the event pre-bucketing logic in FeatureComputer._compute_for_lead."""

from collections import defaultdict
from datetime import datetime, timezone, timedelta

from tests.unit.test_features.conftest import make_test_event


def prebucket(events, as_of_date):
    """Replicate the pre-bucketing logic from FeatureComputer._compute_for_lead."""
    filtered = [e for e in events if e.occurred_at < as_of_date]
    events_by_type: dict[str, list] = defaultdict(list)
    for e in filtered:
        events_by_type[e.event_type].append(e)
    events_by_type["_all"] = filtered
    return dict(events_by_type)


AS_OF = datetime(2026, 3, 15, tzinfo=timezone.utc)


class TestPrebucketFiltering:
    def test_filters_events_at_or_after_as_of_date(self):
        past = make_test_event(event_type="page_view", occurred_at=AS_OF - timedelta(days=1))
        at_boundary = make_test_event(event_type="page_view", occurred_at=AS_OF)
        future = make_test_event(event_type="page_view", occurred_at=AS_OF + timedelta(days=1))
        result = prebucket([past, at_boundary, future], AS_OF)
        assert result["_all"] == [past]
        assert result["page_view"] == [past]

    def test_empty_input_returns_only_all_key(self):
        result = prebucket([], AS_OF)
        assert result == {"_all": []}


class TestPrebucketGrouping:
    def test_groups_by_event_type(self):
        pv = make_test_event(event_type="page_view", occurred_at=AS_OF - timedelta(days=1))
        eo = make_test_event(event_type="email_open", occurred_at=AS_OF - timedelta(days=2))
        ec = make_test_event(event_type="email_click", occurred_at=AS_OF - timedelta(days=3))
        result = prebucket([pv, eo, ec], AS_OF)
        assert result["page_view"] == [pv]
        assert result["email_open"] == [eo]
        assert result["email_click"] == [ec]
        assert sorted(result["_all"], key=id) == sorted([pv, eo, ec], key=id)

    def test_multiple_events_same_type(self):
        pv1 = make_test_event(event_type="page_view", occurred_at=AS_OF - timedelta(days=1))
        pv2 = make_test_event(event_type="page_view", occurred_at=AS_OF - timedelta(days=2))
        result = prebucket([pv1, pv2], AS_OF)
        assert result["page_view"] == [pv1, pv2]
        assert len(result["_all"]) == 2

    def test_all_key_contains_full_filtered_list(self):
        events = [
            make_test_event(event_type="page_view", occurred_at=AS_OF - timedelta(days=1)),
            make_test_event(event_type="email_open", occurred_at=AS_OF - timedelta(days=2)),
            make_test_event(event_type="form_submission", occurred_at=AS_OF - timedelta(days=3)),
        ]
        result = prebucket(events, AS_OF)
        assert len(result["_all"]) == 3

    def test_missing_type_not_in_dict(self):
        pv = make_test_event(event_type="page_view", occurred_at=AS_OF - timedelta(days=1))
        result = prebucket([pv], AS_OF)
        assert "email_open" not in result
        assert result.get("email_open", []) == []
