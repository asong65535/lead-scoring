# tests/integration/test_db.py
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.models import CRMSyncLog, Lead, ModelRegistry, Prediction
from tests.conftest import make_lead_kwargs


async def test_create_and_read_lead(db_session):
    lead = Lead(**make_lead_kwargs())
    db_session.add(lead)
    await db_session.flush()

    result = await db_session.execute(select(Lead).where(Lead.id == lead.id))
    fetched = result.scalar_one()
    assert fetched.external_id == lead.external_id
    assert fetched.source_system == "kaggle"


async def test_lead_defaults(db_session):
    lead = Lead(**make_lead_kwargs())
    db_session.add(lead)
    await db_session.flush()

    assert lead.do_not_email is False
    assert lead.do_not_call is False


async def test_create_prediction_for_lead(db_session):
    lead = Lead(**make_lead_kwargs())
    db_session.add(lead)
    await db_session.flush()

    prediction = Prediction(
        lead_id=lead.id,
        score=0.85,
        bucket="A",
        model_version="v1.0",
        feature_snapshot={"total_visits": 10},
        top_factors={"total_visits": 0.3},
    )
    db_session.add(prediction)
    await db_session.flush()

    result = await db_session.execute(
        select(Prediction).where(Prediction.lead_id == lead.id)
    )
    fetched = result.scalar_one()
    assert fetched.score == 0.85
    assert fetched.bucket == "A"


async def test_prediction_invalid_bucket_rejected(db_session):
    lead = Lead(**make_lead_kwargs())
    db_session.add(lead)
    await db_session.flush()

    prediction = Prediction(
        lead_id=lead.id, score=0.5, bucket="X", model_version="v1.0",
    )
    db_session.add(prediction)
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_create_model_registry_entry(db_session):
    entry = ModelRegistry(
        version="v1.0",
        artifact_path="models/v1.0.joblib",
        metrics={"auc": 0.92},
        trained_at=datetime.now(timezone.utc),
    )
    db_session.add(entry)
    await db_session.flush()

    result = await db_session.execute(
        select(ModelRegistry).where(ModelRegistry.version == "v1.0")
    )
    fetched = result.scalar_one()
    assert fetched.metrics["auc"] == 0.92


async def test_create_crm_sync_log(db_session):
    lead = Lead(**make_lead_kwargs())
    db_session.add(lead)
    await db_session.flush()

    log = CRMSyncLog(
        lead_id=lead.id,
        source_system="hubspot",
        action="score_update",
        payload={"score": 0.85},
    )
    db_session.add(log)
    await db_session.flush()

    assert log.status == "pending"
    assert log.error_message is None


async def test_crm_sync_log_invalid_status_rejected(db_session):
    lead = Lead(**make_lead_kwargs())
    db_session.add(lead)
    await db_session.flush()

    log = CRMSyncLog(
        lead_id=lead.id,
        source_system="hubspot",
        action="score_update",
        status="invalid",
    )
    db_session.add(log)
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()
