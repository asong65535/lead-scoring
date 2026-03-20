"""Frequency feature definitions."""

from datetime import datetime, timedelta

from src.services.features.registry import registry


@registry.register("total_pageviews_7d")
def total_pageviews_7d(lead, events, as_of_date: datetime):
    window_start = as_of_date - timedelta(days=7)
    return sum(
        1 for e in events
        if e.event_type == "page_view" and window_start <= e.occurred_at < as_of_date
    )


@registry.register("total_pageviews_30d")
def total_pageviews_30d(lead, events, as_of_date: datetime):
    window_start = as_of_date - timedelta(days=30)
    return sum(
        1 for e in events
        if e.event_type == "page_view" and window_start <= e.occurred_at < as_of_date
    )


@registry.register("total_sessions")
def total_sessions(lead, events, as_of_date: datetime):
    session_ids = set()
    for e in events:
        if e.event_type == "page_view" and e.properties:
            sid = e.properties.get("session_id")
            if sid:
                session_ids.add(sid)
    return len(session_ids)


@registry.register("emails_opened_30d")
def emails_opened_30d(lead, events, as_of_date: datetime):
    window_start = as_of_date - timedelta(days=30)
    return sum(
        1 for e in events
        if e.event_type == "email_open" and window_start <= e.occurred_at < as_of_date
    )


@registry.register("emails_clicked_30d")
def emails_clicked_30d(lead, events, as_of_date: datetime):
    window_start = as_of_date - timedelta(days=30)
    return sum(
        1 for e in events
        if e.event_type == "email_click" and window_start <= e.occurred_at < as_of_date
    )
