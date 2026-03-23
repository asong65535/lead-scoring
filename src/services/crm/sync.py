"""CRM sync service.

Orchestrates score writeback to CRM systems. Logs each attempt to
crm_sync_log for auditability and retry support.
"""
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.crm_sync_log import CRMSyncLog
from src.services.crm.base import CRMClient
from src.services.crm.errors import CRMError
from src.services.scoring import ScoreResult

logger = structlog.get_logger()

CRM_SOURCE_SYSTEMS = {"hubspot", "salesforce"}


class CRMSyncService:
    """Orchestrates score writeback to the CRM."""

    def __init__(self, crm_client: CRMClient, session: AsyncSession):
        self._crm_client = crm_client
        self._session = session

    async def trigger_writeback(self, lead: Any, score_result: ScoreResult) -> None:
        if lead.source_system not in CRM_SOURCE_SYSTEMS:
            return

        payload = {
            "score": score_result.score,
            "bucket": score_result.bucket,
            "top_factors": score_result.top_factors,
            "model_version": score_result.model_version,
        }

        sync_log = CRMSyncLog(
            lead_id=score_result.lead_id,
            source_system=lead.source_system,
            external_id=lead.external_id,
            action="score_update",
            payload=payload,
            status="pending",
        )

        try:
            await self._crm_client.push_score(
                external_id=lead.external_id,
                score=score_result.score,
                bucket=score_result.bucket,
                top_factors=score_result.top_factors,
                model_version=score_result.model_version,
            )
            sync_log.status = "success"
            sync_log.synced_at = datetime.now(timezone.utc)
            logger.info(
                "crm_writeback_success",
                lead_id=str(score_result.lead_id),
                external_id=lead.external_id,
            )
        except CRMError as exc:
            sync_log.status = "failed"
            sync_log.error_message = str(exc)
            logger.warning(
                "crm_writeback_failed",
                lead_id=str(score_result.lead_id),
                external_id=lead.external_id,
                error=str(exc),
            )
        except Exception as exc:
            sync_log.status = "failed"
            sync_log.error_message = str(exc)
            logger.error(
                "crm_writeback_unexpected_error",
                lead_id=str(score_result.lead_id),
                error=str(exc),
                exc_info=True,
            )

        self._session.add(sync_log)
        await self._session.flush()
