"""Integration tests for FeatureComputer against real Postgres."""

from datetime import datetime, timezone, timedelta
from uuid import UUID

import pytest
from sqlalchemy import select, text, delete
from sqlalchemy.dialects.postgresql import insert

from src.models import Event, Lead
from src.services.features.computer import FeatureComputer
from tests.conftest import make_lead_kwargs, make_event_kwargs

# Track IDs for cleanup
_created_lead_ids: list[UUID] = []


@pytest.fixture
def computer(async_test_engine):
    return FeatureComputer(engine=async_test_engine)


async def _insert_lead_with_events(engine, events_data):
    """Insert a lead + events with a real commit. Returns lead_id."""
    lead_kwargs = make_lead_kwargs()
    async with engine.begin() as conn:
        result = await conn.execute(
            insert(Lead.__table__).values(**lead_kwargs).returning(Lead.__table__.c.id)
        )
        lead_id = result.scalar_one()
        _created_lead_ids.append(lead_id)

        for evt in events_data:
            evt_kwargs = make_event_kwargs(**evt)
            evt_kwargs["lead_id"] = lead_id
            await conn.execute(insert(Event.__table__).values(**evt_kwargs))

    return lead_id


async def _cleanup(engine):
    async with engine.begin() as conn:
        for lid in _created_lead_ids:
            await conn.execute(delete(Event.__table__).where(Event.__table__.c.lead_id == lid))
            await conn.execute(delete(Lead.__table__).where(Lead.__table__.c.id == lid))
    _created_lead_ids.clear()


async def test_compute_returns_all_features(async_test_engine, computer):
    as_of = datetime(2026, 3, 15, tzinfo=timezone.utc)
    lead_id = await _insert_lead_with_events(async_test_engine, [
        {"event_type": "page_view", "occurred_at": as_of - timedelta(days=2)},
        {"event_type": "email_open", "occurred_at": as_of - timedelta(days=5)},
    ])

    result = await computer.compute(lead_id, as_of_date=as_of)

    assert result["lead_id"] == lead_id
    assert "computed_at" in result
    assert len([k for k in result if k not in ("lead_id", "computed_at")]) == 20

    await _cleanup(async_test_engine)


async def test_compute_recency_values(async_test_engine, computer):
    as_of = datetime(2026, 3, 15, tzinfo=timezone.utc)
    lead_id = await _insert_lead_with_events(async_test_engine, [
        {"event_type": "page_view", "occurred_at": as_of - timedelta(days=3)},
        {"event_type": "email_open", "occurred_at": as_of - timedelta(days=7)},
    ])

    result = await computer.compute(lead_id, as_of_date=as_of)

    assert result["days_since_last_visit"] == 3
    assert result["days_since_last_email_open"] == 7
    assert result["days_since_first_touch"] == 7

    await _cleanup(async_test_engine)


async def test_compute_point_in_time_excludes_future_events(async_test_engine, computer):
    as_of = datetime(2026, 3, 10, tzinfo=timezone.utc)
    lead_id = await _insert_lead_with_events(async_test_engine, [
        {"event_type": "page_view", "occurred_at": datetime(2026, 3, 5, tzinfo=timezone.utc)},
        {"event_type": "page_view", "occurred_at": datetime(2026, 3, 12, tzinfo=timezone.utc)},
    ])

    result = await computer.compute(lead_id, as_of_date=as_of)

    assert result["days_since_last_visit"] == 5
    assert result["total_pageviews_7d"] == 1

    await _cleanup(async_test_engine)


async def test_compute_defaulted_features_use_yaml_defaults(async_test_engine, computer):
    as_of = datetime(2026, 3, 15, tzinfo=timezone.utc)
    lead_id = await _insert_lead_with_events(async_test_engine, [])

    result = await computer.compute(lead_id, as_of_date=as_of)

    assert result["company_size_bucket"] == "unknown"
    assert result["industry_match_icp"] is False
    assert result["job_title_seniority"] == "unknown"

    await _cleanup(async_test_engine)


async def test_compute_batch(async_test_engine, computer):
    as_of = datetime(2026, 3, 15, tzinfo=timezone.utc)

    lead1_id = await _insert_lead_with_events(async_test_engine, [
        {"event_type": "page_view", "occurred_at": as_of - timedelta(days=1)},
    ])
    lead2_id = await _insert_lead_with_events(async_test_engine, [
        {"event_type": "email_open", "occurred_at": as_of - timedelta(days=10)},
    ])

    as_of_dates = {lead1_id: as_of, lead2_id: as_of}
    results = await computer.compute_batch([lead1_id, lead2_id], as_of_dates=as_of_dates)

    assert len(results) == 2
    by_lead = {r["lead_id"]: r for r in results}
    assert by_lead[lead1_id]["days_since_last_visit"] == 1
    assert by_lead[lead2_id]["days_since_last_visit"] == 365

    await _cleanup(async_test_engine)
