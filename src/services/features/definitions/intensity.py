"""Intensity feature definitions."""

from collections import defaultdict
from datetime import datetime

from src.services.features.registry import registry


@registry.register("avg_pages_per_session")
def avg_pages_per_session(lead, events, as_of_date: datetime):
    sessions = defaultdict(int)
    for e in events:
        if e.event_type == "page_view" and e.properties:
            sid = e.properties.get("session_id")
            if sid:
                sessions[sid] += 1
    if not sessions:
        return 0
    return sum(sessions.values()) / len(sessions)


@registry.register("avg_session_duration_seconds")
def avg_session_duration_seconds(lead, events, as_of_date: datetime):
    sessions = defaultdict(list)
    for e in events:
        if e.event_type == "page_view" and e.properties:
            sid = e.properties.get("session_id")
            if sid:
                sessions[sid].append(e.occurred_at)
    if not sessions:
        return 0
    durations = []
    for timestamps in sessions.values():
        if len(timestamps) < 2:
            durations.append(0)
        else:
            duration = (max(timestamps) - min(timestamps)).total_seconds()
            durations.append(duration)
    return sum(durations) / len(durations)


@registry.register("pricing_page_views")
def pricing_page_views(lead, events, as_of_date: datetime):
    return sum(
        1 for e in events
        if e.event_type == "page_view" and e.event_name == "Pricing"
    )
