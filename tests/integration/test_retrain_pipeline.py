"""Integration test for the full retrain pipeline.

Requires: Postgres running with leads + events data.
Exercises the real training, comparison, and persistence path.
"""

import pytest
from unittest.mock import patch, AsyncMock
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.dialects.postgresql import insert

from config.settings import get_settings
from src.models import Event, Lead, ModelRegistry
from src.models.retraining_run import RetrainingRun
from scripts.generate_events import generate_events
from scripts.retrain import execute_retrain
from tests.conftest import make_lead_kwargs

_created_lead_ids: list[UUID] = []
_created_model_versions: list[str] = []


@pytest.fixture(autouse=True)
async def cleanup(async_test_engine):
    yield
    async with async_test_engine.begin() as conn:
        for ver in _created_model_versions:
            await conn.execute(
                delete(RetrainingRun.__table__).where(
                    RetrainingRun.__table__.c.candidate_version == ver
                )
            )
            await conn.execute(
                delete(ModelRegistry.__table__).where(
                    ModelRegistry.__table__.c.version == ver
                )
            )
        for lid in _created_lead_ids:
            await conn.execute(delete(Event.__table__).where(Event.__table__.c.lead_id == lid))
            await conn.execute(delete(Lead.__table__).where(Lead.__table__.c.id == lid))
    _created_lead_ids.clear()
    _created_model_versions.clear()


async def _seed_leads(engine, n_converted=20, n_not_converted=30):
    """Insert test leads with converted labels."""
    async with engine.begin() as conn:
        for _ in range(n_converted):
            kwargs = make_lead_kwargs(converted=True)
            result = await conn.execute(
                insert(Lead.__table__).values(**kwargs).returning(Lead.__table__.c.id)
            )
            _created_lead_ids.append(result.scalar_one())
        for _ in range(n_not_converted):
            kwargs = make_lead_kwargs(converted=False)
            result = await conn.execute(
                insert(Lead.__table__).values(**kwargs).returning(Lead.__table__.c.id)
            )
            _created_lead_ids.append(result.scalar_one())


async def test_execute_retrain_records_run(async_test_engine, tmp_path):
    """Full retrain pipeline: seed data -> train real model -> persist run record with valid metrics."""
    await _seed_leads(async_test_engine, n_converted=20, n_not_converted=30)
    await generate_events(engine=async_test_engine, seed=42)

    settings = get_settings()

    with (
        patch("scripts.retrain.trigger_hot_reload", new_callable=AsyncMock, return_value=True),
        patch("scripts.retrain.send_alert", new_callable=AsyncMock, return_value=True),
        patch("scripts.retrain.save_model") as mock_save,
    ):
        mock_save.side_effect = lambda model, version, metrics, hyperparameters, feature_columns, **kw: tmp_path / f"{version}.joblib"

        summary = await execute_retrain(
            engine=async_test_engine,
            tune=False,
            force=True,
            dry_run=False,
            settings=settings,
        )

    _created_model_versions.append(summary["candidate_version"])

    # First run with force=True should always succeed
    assert summary["run_status"] == "success"
    assert summary["promoted"] is True
    assert summary["candidate_version"].startswith("v")

    # The real comparison ran against None (no prior model)
    assert summary["comparison"].current_metrics is None
    assert summary["comparison"].should_promote is True

    # Candidate metrics came from real training — they should be valid ML metrics
    candidate_metrics = summary["comparison"].candidate_metrics
    assert 0.0 < candidate_metrics["auc_roc"] <= 1.0
    assert candidate_metrics["calibration_error"] >= 0.0

    # Verify the run was recorded in the database with correct data
    session_factory = async_sessionmaker(
        bind=async_test_engine, class_=AsyncSession, expire_on_commit=False,
    )
    async with session_factory() as session:
        result = await session.execute(
            select(RetrainingRun)
            .where(RetrainingRun.candidate_version == summary["candidate_version"])
        )
        run = result.scalar_one()

    assert run.run_status == "success"
    assert run.promoted is True
    assert run.triggered_by == "force"
    assert run.active_version_before is None  # first run, no prior model
    assert run.duration_seconds > 0

    # candidate_metrics in DB should match what training produced
    assert run.candidate_metrics["auc_roc"] == candidate_metrics["auc_roc"]

    # training_data_stats should reflect the seeded data
    stats = run.training_data_stats
    assert stats["total_rows"] == stats["train_rows"] + stats["test_rows"]
    assert 0.0 < stats["train_positive_rate"] < 1.0

    # feature_baselines should have entries for real features
    assert len(run.feature_baselines) > 0
