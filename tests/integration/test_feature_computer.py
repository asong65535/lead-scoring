"""Integration tests for FeatureComputer against real Postgres."""

from datetime import datetime, timezone, timedelta
from uuid import UUID

import pytest
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from src.models import Event, Lead
from src.services.features.computer import FeatureComputer
from scripts.generate_events import generate_events
from tests.conftest import make_lead_kwargs, make_event_kwargs

# Track IDs for cleanup
_created_lead_ids: list[UUID] = []


@pytest.fixture
def computer(async_test_engine):
    return FeatureComputer(engine=async_test_engine)


@pytest.fixture(autouse=True)
async def cleanup_after_test(async_test_engine):
    """Ensure test data is cleaned up even if assertions fail."""
    yield
    if _created_lead_ids:
        await _cleanup(async_test_engine)


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


async def test_compute_point_in_time_excludes_future_events(async_test_engine, computer):
    as_of = datetime(2026, 3, 10, tzinfo=timezone.utc)
    lead_id = await _insert_lead_with_events(async_test_engine, [
        {"event_type": "page_view", "occurred_at": datetime(2026, 3, 5, tzinfo=timezone.utc)},
        {"event_type": "page_view", "occurred_at": datetime(2026, 3, 12, tzinfo=timezone.utc)},
    ])

    result = await computer.compute(lead_id, as_of_date=as_of)

    assert result["days_since_last_visit"] == 5
    assert result["total_pageviews_7d"] == 1


async def test_compute_defaulted_features_use_yaml_defaults(async_test_engine, computer):
    as_of = datetime(2026, 3, 15, tzinfo=timezone.utc)
    lead_id = await _insert_lead_with_events(async_test_engine, [])

    result = await computer.compute(lead_id, as_of_date=as_of)

    assert result["company_size_bucket"] == "unknown"
    assert result["industry_match_icp"] is False
    assert result["job_title_seniority"] == "unknown"


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
    assert lead1_id in results
    assert lead2_id in results
    assert results[lead1_id]["days_since_last_visit"] == 1
    assert results[lead2_id]["days_since_last_visit"] == 365


async def test_end_to_end_with_generated_events(async_test_engine, computer):
    """Full pipeline: create converted lead → generate events → compute features."""
    lead_kwargs = make_lead_kwargs(converted=True)
    async with async_test_engine.begin() as conn:
        result = await conn.execute(
            insert(Lead.__table__).values(**lead_kwargs).returning(Lead.__table__.c.id)
        )
        lead_id = result.scalar_one()
        _created_lead_ids.append(lead_id)

    summary = await generate_events(engine=async_test_engine, seed=99)
    assert summary["leads_processed"] >= 1

    # Fetch the converted_at that the generator set
    async with async_test_engine.connect() as conn:
        result = await conn.execute(
            select(Lead.__table__.c.converted_at).where(Lead.__table__.c.id == lead_id)
        )
        converted_at = result.scalar_one()

    assert converted_at is not None

    as_of = converted_at - timedelta(days=1)
    features = await computer.compute(lead_id, as_of_date=as_of)

    # All 20 features present + lead_id + computed_at
    feature_keys = [k for k in features if k not in ("lead_id", "computed_at")]
    assert len(feature_keys) == 20

    # Type correctness
    for key in feature_keys:
        val = features[key]
        assert val is not None, f"{key} is None"
        assert not (isinstance(val, float) and (val != val)), f"{key} is NaN"

    # Converted lead should have some engagement signals
    assert features["days_since_last_visit"] < 365
    assert features["days_since_first_touch"] > 0
