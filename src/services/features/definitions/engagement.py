"""Engagement trend feature definitions."""

from datetime import datetime, timedelta

from src.services.features.registry import registry


def _engagement_score(events, start, end):
    """Count events in [start, end), treating email_unsubscribe as -1."""
    score = 0
    for e in events:
        if start <= e.occurred_at < end:
            if e.event_type == "email_unsubscribe":
                score -= 1
            else:
                score += 1
    return score


@registry.register("engagement_velocity_7d")
def engagement_velocity_7d(lead, events, as_of_date: datetime):
    midpoint = as_of_date - timedelta(days=3.5)
    window_start = as_of_date - timedelta(days=7)
    recent = _engagement_score(events, midpoint, as_of_date)
    older = _engagement_score(events, window_start, midpoint)
    return recent - older


@registry.register("is_engagement_increasing")
def is_engagement_increasing(lead, events, as_of_date: datetime):
    return engagement_velocity_7d(lead, events, as_of_date) > 0
