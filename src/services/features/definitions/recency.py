"""Recency feature definitions."""

from datetime import datetime

from src.services.features.registry import registry


@registry.register("days_since_last_visit")
def days_since_last_visit(lead, events, as_of_date: datetime):
    page_views = [e for e in events if e.event_type == "page_view"]
    if not page_views:
        return 365
    latest = max(e.occurred_at for e in page_views)
    return (as_of_date - latest).days


@registry.register("days_since_last_email_open")
def days_since_last_email_open(lead, events, as_of_date: datetime):
    opens = [e for e in events if e.event_type == "email_open"]
    if not opens:
        return 365
    latest = max(e.occurred_at for e in opens)
    return (as_of_date - latest).days


@registry.register("days_since_first_touch")
def days_since_first_touch(lead, events, as_of_date: datetime):
    if not events:
        return 0
    earliest = min(e.occurred_at for e in events)
    return (as_of_date - earliest).days
