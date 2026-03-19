"""Integration tests for the ingestion pipeline against a real Postgres instance."""

from pathlib import Path

import pytest
from sqlalchemy import func, select, text

from src.models.lead import Lead
from scripts.seed_db import ingest

FIXTURE_CSV = Path(__file__).resolve().parent.parent / "fixtures" / "leads_sample.csv"
FIXTURE_IDS = ("abc-001", "abc-002", "abc-003", "abc-005", "abc-006")


async def _cleanup(engine):
    """Delete fixture leads by their known external_ids."""
    placeholders = ", ".join(f"'{eid}'" for eid in FIXTURE_IDS)
    async with engine.begin() as conn:
        await conn.execute(text(f"DELETE FROM leads WHERE external_id IN ({placeholders})"))


async def test_ingest_fixture_csv(async_test_engine):
    """Full pipeline: fixture CSV → Postgres with correct types and NULLs."""
    await _cleanup(async_test_engine)

    summary = await ingest(csv_path=FIXTURE_CSV, engine=async_test_engine)

    # Row 4 has no Prospect ID → rejected
    assert summary["total_rejected"] == 1
    # 5 valid rows should be inserted
    assert summary["total_inserted"] == 5

    async with async_test_engine.connect() as conn:
        result = await conn.execute(
            select(Lead.__table__).where(
                Lead.__table__.c.external_id.in_(FIXTURE_IDS)
            ).order_by(Lead.__table__.c.external_id),
        )
        leads = result.all()
        assert len(leads) == 5

        by_ext = {row.external_id: row for row in leads}

        # abc-001: clean row
        lead1 = by_ext["abc-001"]
        assert lead1.country == "India"
        assert lead1.do_not_email is False
        assert lead1.converted is True
        assert lead1.total_visits == 5.0

        # abc-002: "Select" placeholders → NULL
        lead2 = by_ext["abc-002"]
        assert lead2.specialization is None
        assert lead2.city is None
        assert lead2.current_occupation is None
        assert lead2.do_not_email is True
        assert lead2.converted is False

        # abc-005: invalid booleans → False, invalid numerics → NULL
        lead5 = by_ext["abc-005"]
        assert lead5.do_not_email is False
        assert lead5.do_not_call is False
        assert lead5.total_visits is None
        assert lead5.total_time_spent is None

        # abc-006: whitespace handling
        lead6 = by_ext["abc-006"]
        assert lead6.country is None
        assert lead6.specialization == "Specialization"
        assert lead6.city == "Mumbai"
        assert lead6.converted is None

    await _cleanup(async_test_engine)


async def test_ingest_idempotent(async_test_engine):
    """Running ingestion twice should not create duplicates."""
    await _cleanup(async_test_engine)

    summary1 = await ingest(csv_path=FIXTURE_CSV, engine=async_test_engine)
    summary2 = await ingest(csv_path=FIXTURE_CSV, engine=async_test_engine)

    assert summary1["total_inserted"] == 5
    assert summary2["total_inserted"] == 0
    assert summary2["total_skipped"] == 5

    async with async_test_engine.connect() as conn:
        result = await conn.execute(
            select(func.count()).select_from(Lead.__table__).where(
                Lead.__table__.c.external_id.in_(FIXTURE_IDS)
            ),
        )
        assert result.scalar() == 5

    await _cleanup(async_test_engine)
