"""Webhook alerting for retraining events.

Posts JSON payloads to a configurable URL. Fire-and-forget — delivery
failure is logged but never blocks the pipeline.
"""

from datetime import datetime, timezone

import httpx
import structlog

logger = structlog.get_logger()


async def send_alert(
    event_type: str,
    payload: dict,
    webhook_url: str | None = None,
) -> bool:
    """POST an alert payload to the webhook URL.

    Returns True if the alert was delivered successfully, False otherwise.
    If webhook_url is None, logs a debug message and returns False.
    """
    if webhook_url is None:
        logger.debug("alert_skipped", event_type=event_type, reason="no webhook URL configured")
        return False

    body = {
        "event_type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": payload,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(webhook_url, json=body)
            logger.info(
                "alert_sent",
                event_type=event_type,
                status_code=response.status_code,
                webhook_url=webhook_url,
            )
            return True
    except Exception as exc:
        logger.error(
            "alert_delivery_failed",
            event_type=event_type,
            webhook_url=webhook_url,
            error=str(exc),
        )
        return False
