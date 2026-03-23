import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.crm.errors import CRMWritebackError
from src.services.crm.retry import retry_pending_writebacks


def _make_sync_log(status="failed", retry_count=0, updated_at=None, payload=None):
    log = MagicMock()
    log.id = uuid.uuid4()
    log.lead_id = uuid.uuid4()
    log.external_id = "ext-1"
    log.source_system = "hubspot"
    log.status = status
    log.retry_count = retry_count
    log.updated_at = updated_at or (datetime.now(timezone.utc) - timedelta(minutes=10))
    log.payload = payload or {"score": 0.85, "bucket": "A", "top_factors": [], "model_version": "v1.0"}
    log.error_message = None
    log.synced_at = None
    return log


async def test_retries_failed_writebacks():
    crm_client = AsyncMock()
    crm_client.push_score = AsyncMock()

    log = _make_sync_log()
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = [log]
    session.execute = AsyncMock(return_value=result_mock)

    summary = await retry_pending_writebacks(session, crm_client, max_retries=5, delay_seconds=300)

    crm_client.push_score.assert_called_once_with(
        external_id="ext-1", score=0.85, bucket="A", top_factors=[], model_version="v1.0",
    )
    assert log.status == "success"
    assert summary["succeeded"] == 1


async def test_increments_retry_count_on_failure():
    crm_client = AsyncMock()
    crm_client.push_score = AsyncMock(side_effect=CRMWritebackError("fail"))

    log = _make_sync_log(retry_count=2)
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = [log]
    session.execute = AsyncMock(return_value=result_mock)

    summary = await retry_pending_writebacks(session, crm_client, max_retries=5, delay_seconds=300)

    assert log.retry_count == 3
    assert log.status == "failed"
    assert summary["failed"] == 1


async def test_skips_when_no_pending_rows():
    crm_client = AsyncMock()
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=result_mock)

    summary = await retry_pending_writebacks(session, crm_client)

    assert summary["attempted"] == 0
    crm_client.push_score.assert_not_called()
