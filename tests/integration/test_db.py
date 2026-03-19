"""Integration tests for database operations against a real Postgres instance.

Tests verify actual DB enforcement of constraints, not just ORM behavior.
Each test exercises a scenario that could silently break if the schema
or migration diverges from the model definitions.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError

from src.models import CRMSyncLog, Lead, ModelRegistry, Prediction
from tests.conftest import make_lead_kwargs


# ---------------------------------------------------------------------------
# Lead CRUD
# ---------------------------------------------------------------------------

async def test_create_and_read_lead(db_session):
    lead = Lead(**make_lead_kwargs())
    db_session.add(lead)
    await db_session.flush()

    result = await db_session.execute(select(Lead).where(Lead.id == lead.id))
    fetched = result.scalar_one()
    assert fetched.external_id == lead.external_id
    assert fetched.source_system == "kaggle"


async def test_lead_boolean_defaults(db_session):
    lead = Lead(**make_lead_kwargs())
    db_session.add(lead)
    await db_session.flush()

    assert lead.do_not_email is False
    assert lead.do_not_call is False


async def test_update_lead_fields(db_session):
    lead = Lead(**make_lead_kwargs(country="US"))
    db_session.add(lead)
    await db_session.flush()

    lead.country = "UK"
    lead.total_visits = 42.0
    await db_session.flush()

    result = await db_session.execute(select(Lead).where(Lead.id == lead.id))
    fetched = result.scalar_one()
    assert fetched.country == "UK"
    assert fetched.total_visits == 42.0


async def test_lead_duplicate_external_id_rejected(db_session):
    """Unique constraint on external_id must be enforced by the DB."""
    shared_ext_id = "dup-ext-001"
    lead1 = Lead(**make_lead_kwargs(external_id=shared_ext_id))
    db_session.add(lead1)
    await db_session.flush()

    lead2 = Lead(**make_lead_kwargs(external_id=shared_ext_id))
    db_session.add(lead2)
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_lead_without_external_id_rejected(db_session):
    """external_id is NOT NULL — DB must reject missing values."""
    lead = Lead(source_system="kaggle")
    # external_id left as None
    db_session.add(lead)
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_lead_nullable_fields_accept_none(db_session):
    lead = Lead(**make_lead_kwargs())
    db_session.add(lead)
    await db_session.flush()

    assert lead.country is None
    assert lead.total_visits is None
    assert lead.converted is None


# ---------------------------------------------------------------------------
# Prediction CRUD & constraints
# ---------------------------------------------------------------------------

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
        select(Prediction).where(Prediction.lead_id == lead.id),
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


async def test_prediction_each_valid_bucket_accepted(db_session):
    """All four bucket values must be accepted by the CHECK constraint."""
    lead = Lead(**make_lead_kwargs())
    db_session.add(lead)
    await db_session.flush()

    for bucket in ("A", "B", "C", "D"):
        pred = Prediction(
            lead_id=lead.id, score=0.5, bucket=bucket, model_version="v1.0",
        )
        db_session.add(pred)
    await db_session.flush()

    result = await db_session.execute(
        select(Prediction).where(Prediction.lead_id == lead.id),
    )
    buckets = {p.bucket for p in result.scalars().all()}
    assert buckets == {"A", "B", "C", "D"}


async def test_prediction_without_lead_id_rejected(db_session):
    """FK constraint — prediction must reference an existing lead."""
    import uuid
    prediction = Prediction(
        lead_id=uuid.uuid4(),  # non-existent lead
        score=0.5,
        bucket="A",
        model_version="v1.0",
    )
    db_session.add(prediction)
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_prediction_jsonb_stores_and_retrieves_complex_data(db_session):
    lead = Lead(**make_lead_kwargs())
    db_session.add(lead)
    await db_session.flush()

    snapshot = {"total_visits": 10, "nested": {"a": [1, 2, 3]}}
    factors = [{"feature": "visits", "impact": 0.3}]
    pred = Prediction(
        lead_id=lead.id, score=0.7, bucket="B", model_version="v1.0",
        feature_snapshot=snapshot, top_factors=factors,
    )
    db_session.add(pred)
    await db_session.flush()

    result = await db_session.execute(
        select(Prediction).where(Prediction.id == pred.id),
    )
    fetched = result.scalar_one()
    assert fetched.feature_snapshot["nested"]["a"] == [1, 2, 3]
    assert fetched.top_factors[0]["impact"] == 0.3


# ---------------------------------------------------------------------------
# Relationship traversal
# ---------------------------------------------------------------------------

async def test_lead_predictions_relationship(db_session):
    lead = Lead(**make_lead_kwargs())
    db_session.add(lead)
    await db_session.flush()

    for score in (0.3, 0.7):
        pred = Prediction(
            lead_id=lead.id, score=score, bucket="B", model_version="v1.0",
        )
        db_session.add(pred)
    await db_session.flush()

    await db_session.refresh(lead, attribute_names=["predictions"])
    assert len(lead.predictions) == 2
    scores = {p.score for p in lead.predictions}
    assert scores == {0.3, 0.7}


async def test_lead_sync_logs_relationship(db_session):
    lead = Lead(**make_lead_kwargs())
    db_session.add(lead)
    await db_session.flush()

    log = CRMSyncLog(
        lead_id=lead.id, source_system="hubspot", action="score_update",
    )
    db_session.add(log)
    await db_session.flush()

    await db_session.refresh(lead, attribute_names=["sync_logs"])
    assert len(lead.sync_logs) == 1
    assert lead.sync_logs[0].action == "score_update"


# ---------------------------------------------------------------------------
# ModelRegistry
# ---------------------------------------------------------------------------

async def test_create_model_registry_entry(db_session):
    entry = ModelRegistry(
        version="v-int-1",
        artifact_path="models/v1.0.joblib",
        metrics={"auc": 0.92},
        trained_at=datetime.now(timezone.utc),
    )
    db_session.add(entry)
    await db_session.flush()

    result = await db_session.execute(
        select(ModelRegistry).where(ModelRegistry.version == "v-int-1"),
    )
    fetched = result.scalar_one()
    assert fetched.metrics["auc"] == 0.92
    assert fetched.is_active is False  # default


async def test_model_registry_duplicate_version_rejected(db_session):
    entry1 = ModelRegistry(
        version="v-dup-1",
        artifact_path="models/a.joblib",
        trained_at=datetime.now(timezone.utc),
    )
    db_session.add(entry1)
    await db_session.flush()

    entry2 = ModelRegistry(
        version="v-dup-1",
        artifact_path="models/b.joblib",
        trained_at=datetime.now(timezone.utc),
    )
    db_session.add(entry2)
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_model_registry_without_artifact_path_rejected(db_session):
    entry = ModelRegistry(
        version="v-no-path",
        trained_at=datetime.now(timezone.utc),
    )
    # artifact_path left as None
    db_session.add(entry)
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


# ---------------------------------------------------------------------------
# CRMSyncLog
# ---------------------------------------------------------------------------

async def test_create_crm_sync_log_with_defaults(db_session):
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
    assert log.synced_at is None


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


async def test_crm_sync_log_each_valid_status_accepted(db_session):
    lead = Lead(**make_lead_kwargs())
    db_session.add(lead)
    await db_session.flush()

    for status in ("success", "failed", "pending"):
        log = CRMSyncLog(
            lead_id=lead.id,
            source_system="hubspot",
            action="test_action",
            status=status,
        )
        db_session.add(log)
    await db_session.flush()

    result = await db_session.execute(
        select(CRMSyncLog).where(CRMSyncLog.lead_id == lead.id),
    )
    statuses = {l.status for l in result.scalars().all()}
    assert statuses == {"success", "failed", "pending"}


async def test_crm_sync_log_update_status_and_error(db_session):
    lead = Lead(**make_lead_kwargs())
    db_session.add(lead)
    await db_session.flush()

    log = CRMSyncLog(
        lead_id=lead.id, source_system="hubspot", action="score_update",
    )
    db_session.add(log)
    await db_session.flush()

    log.status = "failed"
    log.error_message = "Connection timeout after 30s"
    await db_session.flush()

    result = await db_session.execute(
        select(CRMSyncLog).where(CRMSyncLog.id == log.id),
    )
    fetched = result.scalar_one()
    assert fetched.status == "failed"
    assert "timeout" in fetched.error_message


async def test_crm_sync_log_without_lead_rejected(db_session):
    """FK constraint — sync log must reference an existing lead."""
    import uuid
    log = CRMSyncLog(
        lead_id=uuid.uuid4(),
        source_system="hubspot",
        action="score_update",
    )
    db_session.add(log)
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()
