"""Retry sweep for failed CRM writebacks.

Queries crm_sync_log for rows in failed/pending state that have not
exceeded the retry ceiling, then re-attempts the push_score call and
updates each row in place. Designed to be called from a cron script.
"""
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.crm_sync_log import CRMSyncLog
from src.services.crm.base import CRMClient
from src.services.crm.errors import CRMError

logger = structlog.get_logger()


async def retry_pending_writebacks(
    session: AsyncSession,
    crm_client: CRMClient,
    max_retries: int = 5,
    delay_seconds: int = 300,
) -> dict[str, int]:
    """Retry failed/pending CRM sync log entries.

    Args:
        session: Async SQLAlchemy session.
        crm_client: CRM client to push scores through.
        max_retries: Skip rows that have already been retried this many times.
        delay_seconds: Only pick up rows whose updated_at is older than this.

    Returns:
        Summary dict with keys: attempted, succeeded, failed.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=delay_seconds)

    result = await session.execute(
        select(CRMSyncLog).where(
            CRMSyncLog.status.in_(["pending", "failed"]),
            CRMSyncLog.retry_count < max_retries,
            CRMSyncLog.updated_at < cutoff,
        )
    )
    logs = result.scalars().all()

    summary: dict[str, int] = {"attempted": len(logs), "succeeded": 0, "failed": 0}

    for log in logs:
        try:
            await crm_client.push_score(
                external_id=log.external_id,
                score=log.payload["score"],
                bucket=log.payload["bucket"],
                top_factors=log.payload.get("top_factors", []),
                model_version=log.payload["model_version"],
            )
            log.status = "success"
            log.synced_at = datetime.now(timezone.utc)
            summary["succeeded"] += 1
            logger.info("retry_writeback_success", sync_log_id=str(log.id))
        except CRMError as exc:
            log.retry_count += 1
            log.error_message = str(exc)
            summary["failed"] += 1
            logger.warning(
                "retry_writeback_failed",
                sync_log_id=str(log.id),
                retry_count=log.retry_count,
                error=str(exc),
            )
        except Exception as exc:
            log.retry_count += 1
            log.error_message = str(exc)
            summary["failed"] += 1
            logger.error(
                "retry_writeback_unexpected_error",
                sync_log_id=str(log.id),
                error=str(exc),
                exc_info=True,
            )

    await session.commit()
    logger.info("retry_sweep_complete", **summary)
    return summary
