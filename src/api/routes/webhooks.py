"""Webhook stub endpoints for CRM integrations.

CRM webhook processing is deferred to Phase 7 (CRM Integration).
These stubs accept and log payloads to validate the webhook delivery
pipeline. Actual event processing (contact sync, rescoring) will be
implemented when the CRM client abstraction is built.
"""

import structlog
from fastapi import APIRouter, Request

logger = structlog.get_logger()

router = APIRouter()


@router.post("/hubspot")
async def hubspot_webhook(request: Request) -> dict:
    # CRM webhook processing is deferred to Phase 7 (CRM Integration).
    # This stub accepts and logs payloads to validate the webhook delivery
    # pipeline. Actual event processing (contact sync, rescoring) will be
    # implemented when the CRM client abstraction is built.
    payload = await request.json()
    logger.info("hubspot_webhook_received", payload_size=len(str(payload)))
    return {"status": "received"}


@router.post("/salesforce")
async def salesforce_webhook(request: Request) -> dict:
    # CRM webhook processing is deferred to Phase 7 (CRM Integration).
    # This stub accepts and logs payloads to validate the webhook delivery
    # pipeline. Actual event processing (contact sync, rescoring) will be
    # implemented when the CRM client abstraction is built.
    payload = await request.json()
    logger.info("salesforce_webhook_received", payload_size=len(str(payload)))
    return {"status": "received"}
