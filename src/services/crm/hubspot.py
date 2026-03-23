"""HubSpot CRM client using the v3 Contacts API.

Responsibilities:
- push_score: PATCH a contact's properties with scored fields
- fetch_contact: GET a single contact and reverse-map HubSpot field names
- fetch_contacts: POST to the search endpoint with optional filters and pagination
- validate_webhook: verify HubSpot v3 HMAC-SHA256 signature and timestamp freshness
- parse_webhook_event: normalise a raw webhook payload into WebhookEvent dataclasses
"""

import hashlib
import hmac
import json
import time
from typing import Any

import httpx
import structlog

from src.services.crm.base import CRMClient, WebhookEvent
from src.services.crm.errors import (
    CRMContactNotFoundError,
    CRMRateLimitError,
    CRMWritebackError,
)

logger = structlog.get_logger()

HUBSPOT_BASE_URL = "https://api.hubapi.com"
WEBHOOK_TIMESTAMP_MAX_AGE = 300  # 5 minutes


class HubSpotClient(CRMClient):
    """HubSpot CRM client using the v3 API."""

    def __init__(
        self,
        access_token: str,
        client_secret: str | None,
        field_mappings: dict[str, Any],
        timeout: float = 10.0,
        writeback_timeout: float = 3.0,
    ):
        self._access_token = access_token
        self._client_secret = client_secret
        self._output_fields = field_mappings.get("output_fields", {})
        self._contact_fields = field_mappings.get("contact_fields", {})
        self._reverse_contact_fields = {v: k for k, v in self._contact_fields.items()}
        self._timeout = timeout
        self._writeback_timeout = writeback_timeout
        self._http = httpx.AsyncClient(
            base_url=HUBSPOT_BASE_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )

    async def close(self) -> None:
        await self._http.aclose()

    def _check_response(self, response: httpx.Response, external_id: str = "") -> None:
        if response.status_code == 404:
            raise CRMContactNotFoundError(external_id)
        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", "10"))
            raise CRMRateLimitError(retry_after)
        if response.status_code >= 400:
            detail = response.text[:200]
            raise CRMWritebackError(
                f"HubSpot API error {response.status_code}: {detail}"
            )

    async def push_score(
        self,
        external_id: str,
        score: float,
        bucket: str,
        top_factors: list[dict[str, Any]],
        model_version: str,
    ) -> None:
        properties = {}
        if "score" in self._output_fields:
            properties[self._output_fields["score"]] = score
        if "bucket" in self._output_fields:
            properties[self._output_fields["bucket"]] = bucket
        if "top_factors" in self._output_fields:
            properties[self._output_fields["top_factors"]] = json.dumps(top_factors)
        if "model_version" in self._output_fields:
            properties[self._output_fields["model_version"]] = model_version

        response = await self._http.request(
            method="PATCH",
            url=f"/crm/v3/objects/contacts/{external_id}",
            json={"properties": properties},
            timeout=self._writeback_timeout,
        )
        self._check_response(response, external_id)

    async def fetch_contact(self, external_id: str) -> dict[str, Any]:
        hubspot_fields = list(self._contact_fields.values())
        response = await self._http.request(
            method="GET",
            url=f"/crm/v3/objects/contacts/{external_id}",
            params={"properties": ",".join(hubspot_fields)},
        )
        self._check_response(response, external_id)

        data = response.json()
        props = data.get("properties", {})
        return {
            self._reverse_contact_fields.get(k, k): v
            for k, v in props.items()
            if k in self._reverse_contact_fields
        }

    async def fetch_contacts(
        self,
        filters: dict[str, Any] | None = None,
        page_cursor: str | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        body: dict[str, Any] = {"limit": 100}
        if filters:
            body["filterGroups"] = filters
        if page_cursor:
            body["after"] = page_cursor

        response = await self._http.request(
            method="POST",
            url="/crm/v3/objects/contacts/search",
            json=body,
        )
        self._check_response(response)

        data = response.json()
        contacts = []
        for item in data.get("results", []):
            props = item.get("properties", {})
            contacts.append({
                self._reverse_contact_fields.get(k, k): v
                for k, v in props.items()
                if k in self._reverse_contact_fields
            })

        next_cursor = data.get("paging", {}).get("next", {}).get("after")
        return contacts, next_cursor

    async def validate_webhook(
        self, headers: dict[str, str], body: bytes,
    ) -> bool:
        if not self._client_secret:
            logger.warning("webhook_validation_skipped", reason="no client secret configured")
            return False

        signature = headers.get("x-hubspot-signature-v3", "")
        timestamp = headers.get("x-hubspot-request-timestamp", "")
        method = headers.get("x-hubspot-request-method", "POST")
        uri = headers.get("x-hubspot-request-uri", "")

        try:
            ts = int(timestamp)
        except (ValueError, TypeError):
            return False
        if abs(time.time() - ts) > WEBHOOK_TIMESTAMP_MAX_AGE:
            return False

        source = f"{method}{uri}{body.decode()}{timestamp}"
        expected = hmac.new(
            self._client_secret.encode(), source.encode(), hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(signature, expected)

    async def parse_webhook_event(
        self, payload: dict[str, Any] | list[dict[str, Any]],
    ) -> list[WebhookEvent]:
        items = payload if isinstance(payload, list) else [payload]
        events = []
        for item in items:
            object_id = str(item.get("objectId", ""))
            sub_type = item.get("subscriptionType", "")

            if "propertyChange" in sub_type:
                change_type = "property_change"
                changed_fields = [item.get("propertyName", "")]
            else:
                change_type = "engagement"
                changed_fields = []

            events.append(WebhookEvent(
                external_id=object_id,
                change_type=change_type,
                changed_fields=changed_fields,
                raw=item,
            ))
        return events
