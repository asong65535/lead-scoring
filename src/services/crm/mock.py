from typing import Any

from src.services.crm.base import CRMClient, WebhookEvent
from src.services.crm.errors import CRMError


class MockCRMClient(CRMClient):
    """Test double for CRM integrations. Records all calls for assertion."""

    def __init__(
        self,
        push_score_error: CRMError | None = None,
        contact_data: dict[str, Any] | None = None,
        webhook_valid: bool = True,
        webhook_events: list[WebhookEvent] | None = None,
    ):
        self.push_score_error = push_score_error
        self.contact_data = contact_data or {}
        self.webhook_valid = webhook_valid
        self.webhook_events = webhook_events or []
        self.push_score_calls: list[dict[str, Any]] = []
        self.fetch_contact_calls: list[str] = []

    async def push_score(
        self,
        external_id: str,
        score: float,
        bucket: str,
        top_factors: list[dict[str, Any]],
        model_version: str,
    ) -> None:
        self.push_score_calls.append({
            "external_id": external_id,
            "score": score,
            "bucket": bucket,
            "top_factors": top_factors,
            "model_version": model_version,
        })
        if self.push_score_error:
            raise self.push_score_error

    async def fetch_contact(self, external_id: str) -> dict[str, Any]:
        self.fetch_contact_calls.append(external_id)
        return self.contact_data

    async def fetch_contacts(
        self,
        filters: dict[str, Any] | None = None,
        page_cursor: str | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        return [], None

    async def validate_webhook(
        self, headers: dict[str, str], body: bytes,
        method: str, uri: str,
    ) -> bool:
        return self.webhook_valid

    async def parse_webhook_event(
        self, payload: dict[str, Any],
    ) -> list[WebhookEvent]:
        return self.webhook_events
