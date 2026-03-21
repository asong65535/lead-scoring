"""Recency feature definitions."""

from datetime import datetime

from src.services.features.registry import registry


@registry.register("days_since_last_visit")
def days_since_last_visit(lead, events_by_type: dict, as_of_date: datetime):
    page_views = events_by_type.get("page_view", [])
    if not page_views:
        return 365
    latest = max(e.occurred_at for e in page_views)
    return (as_of_date - latest).days


@registry.register("days_since_last_email_open")
def days_since_last_email_open(lead, events_by_type: dict, as_of_date: datetime):
    opens = events_by_type.get("email_open", [])
    if not opens:
        return 365
    latest = max(e.occurred_at for e in opens)
    return (as_of_date - latest).days


@registry.register("days_since_first_touch")
def days_since_first_touch(lead, events_by_type: dict, as_of_date: datetime):
    all_events = events_by_type.get("_all", [])
    if not all_events:
        return 0
    earliest = min(e.occurred_at for e in all_events)
    return (as_of_date - earliest).days
