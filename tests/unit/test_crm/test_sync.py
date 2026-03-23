import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.crm.errors import CRMWritebackError
from src.services.crm.mock import MockCRMClient
from src.services.crm.sync import CRMSyncService
from src.services.scoring import ScoreResult


def _make_score_result(**overrides) -> ScoreResult:
    defaults = {
        "lead_id": uuid.uuid4(),
        "score": 0.85,
        "bucket": "A",
        "model_version": "v1.0",
        "top_factors": [{"feature": "visits", "impact": 0.1, "value": 5}],
        "scored_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    return ScoreResult(**defaults)


def _make_lead(external_id="ext-1", source_system="hubspot"):
    lead = MagicMock()
    lead.id = uuid.uuid4()
    lead.external_id = external_id
    lead.source_system = source_system
    return lead


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def mock_crm():
    return MockCRMClient()


@pytest.fixture
def sync_service(mock_session, mock_crm):
    return CRMSyncService(crm_client=mock_crm, session=mock_session)


class TestTriggerWriteback:
    async def test_success_creates_sync_log_and_pushes_score(self, sync_service, mock_session, mock_crm):
        lead = _make_lead()
        result = _make_score_result(lead_id=lead.id)

        await sync_service.trigger_writeback(lead, result)

        assert mock_session.add.called
        sync_log = mock_session.add.call_args[0][0]
        assert sync_log.action == "score_update"
        assert sync_log.source_system == "hubspot"
        assert sync_log.external_id == "ext-1"
        assert sync_log.status == "success"

        assert len(mock_crm.push_score_calls) == 1

    async def test_failure_logs_error_and_marks_failed(self, mock_session):
        crm = MockCRMClient(push_score_error=CRMWritebackError("timeout"))
        service = CRMSyncService(crm_client=crm, session=mock_session)

        lead = _make_lead()
        result = _make_score_result(lead_id=lead.id)

        await service.trigger_writeback(lead, result)

        sync_log = mock_session.add.call_args[0][0]
        assert sync_log.status == "failed"
        assert "timeout" in sync_log.error_message

    async def test_skips_writeback_for_non_crm_leads(self, sync_service, mock_session, mock_crm):
        lead = _make_lead(source_system="kaggle")
        result = _make_score_result(lead_id=lead.id)

        await sync_service.trigger_writeback(lead, result)

        assert not mock_session.add.called
        assert len(mock_crm.push_score_calls) == 0
