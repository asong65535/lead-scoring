"""Intent signal feature definitions."""

from datetime import datetime

from src.services.features.registry import registry


@registry.register("viewed_pricing")
def viewed_pricing(lead, events_by_type: dict, as_of_date: datetime):
    return any(e.event_name == "Pricing" for e in events_by_type.get("page_view", []))


@registry.register("requested_demo")
def requested_demo(lead, events_by_type: dict, as_of_date: datetime):
    return any(e.event_name == "Demo Request" for e in events_by_type.get("form_submission", []))


@registry.register("downloaded_content")
def downloaded_content(lead, events_by_type: dict, as_of_date: datetime):
    return any(e.event_name == "Content Download" for e in events_by_type.get("form_submission", []))


@registry.register("visited_competitor_comparison")
def visited_competitor_comparison(lead, events_by_type: dict, as_of_date: datetime):
    return any(e.event_name == "Competitor Comparison" for e in events_by_type.get("page_view", []))
