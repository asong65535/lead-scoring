"""Integration tests for the synthetic event generator."""

import uuid

import pytest
from sqlalchemy import func, select, text

from src.models.event import Event, VALID_EVENT_TYPES
from src.models.lead import Lead
from scripts.generate_events import generate_events

# Deterministic external IDs for cleanup
TEST_EXT_IDS = [f"gen-evt-test-{i}" for i in range(5)]


async def _insert_test_leads(engine):
    """Insert test leads: 2 converted, 3 non-converted."""
    leads = []
    for i, ext_id in enumerate(TEST_EXT_IDS):
        leads.append({
            "id": uuid.uuid4(),
            "external_id": ext_id,
            "source_system": "kaggle",
            "converted": i < 2,  # first 2 are converted
            "do_not_email": False,
            "do_not_call": False,
        })
    async with engine.begin() as conn:
        await conn.execute(Lead.__table__.insert().values(leads))
    return leads


async def _cleanup(engine):
    """Delete test leads and their events."""
    placeholders = ", ".join(f"'{eid}'" for eid in TEST_EXT_IDS)
    async with engine.begin() as conn:
        # Events cascade-delete with leads
        await conn.execute(text(f"DELETE FROM leads WHERE external_id IN ({placeholders})"))


async def _get_lead_ids(engine):
    async with engine.connect() as conn:
        result = await conn.execute(
            select(Lead.__table__.c.id).where(
                Lead.__table__.c.external_id.in_(TEST_EXT_IDS)
            )
        )
        return [row.id for row in result.all()]


async def test_generate_events_creates_events(async_test_engine):
    """Events are created for leads without existing events."""
    await _cleanup(async_test_engine)
    leads = await _insert_test_leads(async_test_engine)

    summary = await generate_events(engine=async_test_engine, window_days=90, seed=99)

    assert summary["leads_processed"] >= 5  # at least our 5 test leads
    assert summary["total_events"] > 0
    assert set(summary["events_by_type"].keys()) == set(VALID_EVENT_TYPES)

    # Verify events exist for our test leads
    lead_ids = await _get_lead_ids(async_test_engine)
    async with async_test_engine.connect() as conn:
        result = await conn.execute(
            select(func.count()).select_from(Event.__table__).where(
                Event.__table__.c.lead_id.in_(lead_ids)
            )
        )
        event_count = result.scalar()
        assert event_count > 0

    await _cleanup(async_test_engine)


async def test_generate_events_idempotent(async_test_engine):
    """Second run skips leads that already have events."""
    await _cleanup(async_test_engine)
    await _insert_test_leads(async_test_engine)

    summary1 = await generate_events(engine=async_test_engine, window_days=90, seed=99)
    processed1 = summary1["leads_processed"]
    events1 = summary1["total_events"]

    summary2 = await generate_events(engine=async_test_engine, window_days=90, seed=99)

    # Second run should process zero of our leads (they all have events now)
    assert summary2["leads_processed"] == 0
    assert summary2["total_events"] == 0
    assert summary2["leads_skipped"] >= processed1

    await _cleanup(async_test_engine)


async def test_converted_leads_get_more_events(async_test_engine):
    """Converted leads should have 15-50 events, non-converted 3-20."""
    await _cleanup(async_test_engine)
    leads = await _insert_test_leads(async_test_engine)

    await generate_events(engine=async_test_engine, window_days=90, seed=99)

    lead_ids = await _get_lead_ids(async_test_engine)

    async with async_test_engine.connect() as conn:
        # Get converted lead IDs
        result = await conn.execute(
            select(Lead.__table__.c.id, Lead.__table__.c.converted).where(
                Lead.__table__.c.external_id.in_(TEST_EXT_IDS)
            )
        )
        leads_info = result.all()

        for lead_id, converted in leads_info:
            result = await conn.execute(
                select(func.count()).select_from(Event.__table__).where(
                    Event.__table__.c.lead_id == lead_id
                )
            )
            count = result.scalar()
            if converted:
                assert 15 <= count <= 50, f"Converted lead has {count} events, expected 15-50"
            else:
                assert 3 <= count <= 20, f"Non-converted lead has {count} events, expected 3-20"

    await _cleanup(async_test_engine)


async def test_converted_leads_get_converted_at(async_test_engine):
    """Converted leads should have converted_at set after generation."""
    await _cleanup(async_test_engine)
    await _insert_test_leads(async_test_engine)

    await generate_events(engine=async_test_engine, window_days=90, seed=99)

    async with async_test_engine.connect() as conn:
        result = await conn.execute(
            select(Lead.__table__.c.converted, Lead.__table__.c.converted_at).where(
                Lead.__table__.c.external_id.in_(TEST_EXT_IDS)
            )
        )
        for converted, converted_at in result.all():
            if converted:
                assert converted_at is not None, "Converted lead should have converted_at set"

    await _cleanup(async_test_engine)


async def test_event_properties_structure(async_test_engine):
    """Verify event properties have expected keys per event type."""
    await _cleanup(async_test_engine)
    await _insert_test_leads(async_test_engine)

    await generate_events(engine=async_test_engine, window_days=90, seed=99)

    lead_ids = await _get_lead_ids(async_test_engine)

    async with async_test_engine.connect() as conn:
        result = await conn.execute(
            select(Event.__table__.c.event_type, Event.__table__.c.properties).where(
                Event.__table__.c.lead_id.in_(lead_ids)
            ).limit(200)
        )
        for event_type, props in result.all():
            assert props is not None
            if event_type == "page_view":
                assert "url" in props
                assert "duration_seconds" in props
                assert "session_id" in props
            elif event_type == "email_open":
                assert "email_id" in props
                assert "subject" in props
            elif event_type == "email_click":
                assert "email_id" in props
                assert "link_url" in props
            elif event_type == "form_submission":
                assert "form_id" in props
            elif event_type == "email_unsubscribe":
                assert "email_id" in props

    await _cleanup(async_test_engine)
