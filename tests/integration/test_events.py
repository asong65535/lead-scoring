"""Integration tests for events table against real Postgres."""

import uuid
from datetime import datetime, timezone, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.models import Event, Lead
from tests.conftest import make_event_kwargs, make_lead_kwargs


async def test_create_event_for_lead(db_session):
    lead = Lead(**make_lead_kwargs())
    db_session.add(lead)
    await db_session.flush()

    event = Event(lead_id=lead.id, **make_event_kwargs())
    db_session.add(event)
    await db_session.flush()

    result = await db_session.execute(select(Event).where(Event.lead_id == lead.id))
    fetched = result.scalar_one()
    assert fetched.event_type == "page_view"
    assert fetched.event_name == "Blog Post"


async def test_event_without_lead_rejected(db_session):
    event = Event(lead_id=uuid.uuid4(), **make_event_kwargs())
    db_session.add(event)
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_event_invalid_type_rejected(db_session):
    lead = Lead(**make_lead_kwargs())
    db_session.add(lead)
    await db_session.flush()

    event = Event(lead_id=lead.id, **make_event_kwargs(event_type="invalid_type"))
    db_session.add(event)
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_event_each_valid_type_accepted(db_session):
    lead = Lead(**make_lead_kwargs())
    db_session.add(lead)
    await db_session.flush()

    for etype in ("page_view", "email_open", "email_click", "form_submission", "email_unsubscribe"):
        event = Event(lead_id=lead.id, **make_event_kwargs(event_type=etype))
        db_session.add(event)
    await db_session.flush()

    result = await db_session.execute(select(Event).where(Event.lead_id == lead.id))
    types = {e.event_type for e in result.scalars().all()}
    assert types == {"page_view", "email_open", "email_click", "form_submission", "email_unsubscribe"}


async def test_event_jsonb_round_trip(db_session):
    lead = Lead(**make_lead_kwargs())
    db_session.add(lead)
    await db_session.flush()

    props = {"url": "/pricing", "duration_seconds": 45, "nested": {"a": [1, 2]}}
    event = Event(lead_id=lead.id, **make_event_kwargs(properties=props))
    db_session.add(event)
    await db_session.flush()

    result = await db_session.execute(select(Event).where(Event.id == event.id))
    fetched = result.scalar_one()
    assert fetched.properties["nested"]["a"] == [1, 2]
    assert fetched.properties["duration_seconds"] == 45


async def test_lead_events_relationship(db_session):
    lead = Lead(**make_lead_kwargs())
    db_session.add(lead)
    await db_session.flush()

    now = datetime.now(timezone.utc)
    for i in range(3):
        event = Event(lead_id=lead.id, **make_event_kwargs(
            occurred_at=now - timedelta(days=i),
        ))
        db_session.add(event)
    await db_session.flush()

    await db_session.refresh(lead, attribute_names=["events"])
    assert len(lead.events) == 3


async def test_event_cascade_delete_with_lead(db_session):
    """Events should be deleted when their lead is deleted."""
    lead = Lead(**make_lead_kwargs())
    db_session.add(lead)
    await db_session.flush()

    event = Event(lead_id=lead.id, **make_event_kwargs())
    db_session.add(event)
    await db_session.flush()
    event_id = event.id

    await db_session.delete(lead)
    await db_session.flush()

    result = await db_session.execute(select(Event).where(Event.id == event_id))
    assert result.scalar_one_or_none() is None


async def test_lead_converted_at_nullable(db_session):
    lead = Lead(**make_lead_kwargs())
    db_session.add(lead)
    await db_session.flush()
    assert lead.converted_at is None

    lead.converted_at = datetime.now(timezone.utc)
    await db_session.flush()
    assert lead.converted_at is not None
