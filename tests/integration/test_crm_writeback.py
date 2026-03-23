"""Integration test: scoring a lead creates a crm_sync_log row when CRM is configured."""
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from src.models.crm_sync_log import CRMSyncLog
from src.models.lead import Lead
from src.services.crm.errors import CRMWritebackError
from src.services.crm.mock import MockCRMClient
from src.services.crm.sync import CRMSyncService
from src.services.scoring import ScoreResult
from tests.conftest import make_lead_kwargs


def _make_score_result(lead_id, **overrides):
    defaults = {
        "lead_id": lead_id,
        "score": 0.75,
        "bucket": "A",
        "model_version": "v1.0",
        "top_factors": [{"feature": "visits", "impact": 0.1, "value": 5}],
        "scored_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    return ScoreResult(**defaults)


@pytest.mark.asyncio
async def test_trigger_writeback_creates_sync_log(db_session):
    """Writeback creates a crm_sync_log row with correct fields."""
    lead = Lead(**make_lead_kwargs(source_system="hubspot", external_id=f"hs-{uuid.uuid4().hex[:8]}"))
    db_session.add(lead)
    await db_session.flush()

    crm = MockCRMClient()
    sync_service = CRMSyncService(crm_client=crm, session=db_session)
    score_result = _make_score_result(lead.id)

    await sync_service.trigger_writeback(lead, score_result)

    result = await db_session.execute(
        select(CRMSyncLog).where(CRMSyncLog.lead_id == lead.id)
    )
    log = result.scalar_one()
    assert log.status == "success"
    assert log.action == "score_update"
    assert log.source_system == "hubspot"
    assert log.external_id == lead.external_id
    assert log.synced_at is not None
    assert log.payload["score"] == 0.75
    assert log.payload["bucket"] == "A"
    assert log.payload["model_version"] == "v1.0"
    assert log.payload["top_factors"] == score_result.top_factors


@pytest.mark.asyncio
async def test_trigger_writeback_failure_creates_failed_log(db_session):
    """CRM push failure still persists a sync_log row with status=failed."""
    lead = Lead(**make_lead_kwargs(source_system="hubspot", external_id=f"hs-{uuid.uuid4().hex[:8]}"))
    db_session.add(lead)
    await db_session.flush()

    crm = MockCRMClient(push_score_error=CRMWritebackError("connection refused"))
    sync_service = CRMSyncService(crm_client=crm, session=db_session)
    score_result = _make_score_result(lead.id)

    await sync_service.trigger_writeback(lead, score_result)

    result = await db_session.execute(
        select(CRMSyncLog).where(CRMSyncLog.lead_id == lead.id)
    )
    log = result.scalar_one()
    assert log.status == "failed"
    assert log.synced_at is None
    assert "connection refused" in log.error_message
    assert log.payload["score"] == 0.75
