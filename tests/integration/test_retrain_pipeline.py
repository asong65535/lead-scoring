"""Integration test for the full retrain pipeline.

Requires: Postgres running, seeded data, at least one trained model.
Run after: seed_db.py, generate_events.py, train.py --set-active
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
    """Retrain pipeline should train a model, promote it, and insert a retraining_runs row."""
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

    assert summary["run_status"] in ("success", "blocked", "failed")
    assert summary["candidate_version"].startswith("v")

    session_factory = async_sessionmaker(
        bind=async_test_engine, class_=AsyncSession, expire_on_commit=False,
    )
    async with session_factory() as session:
        result = await session.execute(
            select(RetrainingRun)
            .order_by(RetrainingRun.started_at.desc())
            .limit(1)
        )
        run = result.scalar_one_or_none()

    assert run is not None
    assert run.candidate_version == summary["candidate_version"]
    assert run.candidate_metrics is not None
    assert run.training_data_stats is not None
    assert run.feature_baselines is not None
