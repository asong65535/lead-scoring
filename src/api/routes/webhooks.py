"""Webhook endpoints for CRM integrations.

HubSpot: validates signature, parses events, filters by rescore_triggers,
debounces, and rescores matching leads.
"""
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import get_settings
from src.api.dependencies import get_crm_client, get_scoring_service
from src.models.database import get_session
from src.models.lead import Lead
from src.models.prediction import Prediction
from src.services.crm.base import CRMClient, WebhookEvent
from src.services.scoring import ScoringService

logger = structlog.get_logger()

router = APIRouter()


def _should_rescore(event: WebhookEvent, triggers: dict) -> bool:
    """Check if a webhook event matches the rescore_triggers allowlist."""
    if event.change_type == "property_change":
        allowed = triggers.get("property_changes", [])
        return any(f in allowed for f in event.changed_fields)

    if event.change_type == "engagement":
        allowed = triggers.get("engagement_types", [])
        sub_type = event.raw.get("subscriptionType", "")
        return any(eng_type in sub_type for eng_type in allowed)

    return False


async def _is_debounced(
    session: AsyncSession, lead_id: UUID, debounce_seconds: int,
) -> bool:
    """Check if a lead was scored within the debounce window."""
    result = await session.execute(
        select(Prediction.scored_at)
        .where(Prediction.lead_id == lead_id)
        .order_by(Prediction.scored_at.desc())
        .limit(1)
    )
    last_scored = result.scalar_one_or_none()

    if last_scored is None:
        return False

    cutoff = datetime.now(timezone.utc) - timedelta(seconds=debounce_seconds)
    return last_scored > cutoff


@router.post("/hubspot")
async def hubspot_webhook(
    request: Request,
    session: AsyncSession = Depends(get_session),
    scoring_service: ScoringService = Depends(get_scoring_service),
) -> dict:
    crm_client: CRMClient | None = get_crm_client(request)
    settings = get_settings()

    body = await request.body()

    if crm_client:
        headers = dict(request.headers)
        valid = await crm_client.validate_webhook(headers, body)
        if not valid:
            logger.warning("hubspot_webhook_invalid_signature")
            return {"status": "rejected", "reason": "invalid signature"}

    payload = json.loads(body)
    if crm_client:
        events = await crm_client.parse_webhook_event(payload)
    else:
        logger.info("hubspot_webhook_received_no_crm_client", payload_size=len(body))
        return {"status": "received", "processed": 0}

    crm_mappings = settings.crm_mappings
    triggers = crm_mappings.get("hubspot", {}).get("rescore_triggers", {})
    debounce_seconds = settings.crm.rescore_debounce_seconds

    processed = 0
    for event in events:
        if not _should_rescore(event, triggers):
            logger.debug("webhook_event_filtered", external_id=event.external_id)
            continue

        result = await session.execute(
            select(Lead).where(
                Lead.external_id == event.external_id,
                Lead.source_system == "hubspot",
            )
        )
        lead = result.scalar_one_or_none()
        if lead is None:
            logger.info("webhook_lead_not_found", external_id=event.external_id)
            continue

        if await _is_debounced(session, lead.id, debounce_seconds):
            logger.debug("webhook_debounced", lead_id=str(lead.id))
            continue

        try:
            await scoring_service.score_lead(lead.id)
            processed += 1
            logger.info("webhook_rescore_success", lead_id=str(lead.id))
        except Exception as exc:
            logger.error(
                "webhook_rescore_failed",
                lead_id=str(lead.id),
                error=str(exc),
            )

    return {"status": "received", "processed": processed}


@router.post("/salesforce")
async def salesforce_webhook(request: Request) -> dict:
    payload = await request.json()
    logger.info("salesforce_webhook_received", payload_size=len(str(payload)))
    return {"status": "received", "message": "Salesforce integration not yet implemented"}
