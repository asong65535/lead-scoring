from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class WebhookEvent:
    """Parsed webhook event from a CRM."""

    external_id: str
    change_type: str  # "property_change" or "engagement"
    changed_fields: list[str]
    raw: dict[str, Any]


class CRMClient(ABC):
    """Abstract interface for CRM integrations."""

    @abstractmethod
    async def push_score(
        self,
        external_id: str,
        score: float,
        bucket: str,
        top_factors: list[dict[str, Any]],
        model_version: str,
    ) -> None:
        """Write a lead score back to the CRM."""

    @abstractmethod
    async def fetch_contact(self, external_id: str) -> dict[str, Any]:
        """Fetch a single contact's fields from the CRM."""

    @abstractmethod
    async def fetch_contacts(
        self,
        filters: dict[str, Any] | None = None,
        page_cursor: str | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Fetch a page of contacts. Returns (contacts, next_cursor)."""

    @abstractmethod
    async def validate_webhook(
        self, headers: dict[str, str], body: bytes,
    ) -> bool:
        """Verify that a webhook request is authentic."""

    @abstractmethod
    async def parse_webhook_event(
        self, payload: dict[str, Any],
    ) -> list[WebhookEvent]:
        """Parse a webhook payload into structured events."""
