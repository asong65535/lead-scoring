"""CRM client factory.

Returns the appropriate CRMClient implementation based on the configured
crm.type setting, or None when CRM integration is disabled.
"""

from config.settings import Settings
from src.services.crm.base import CRMClient
from src.services.crm.hubspot import HubSpotClient


def get_crm_client(settings: Settings) -> CRMClient | None:
    """Return the correct CRM client based on settings, or None if CRM is disabled."""
    crm_type = settings.crm.type

    if crm_type == "none":
        return None

    if crm_type == "hubspot":
        mappings = settings.crm_mappings.get("hubspot", {})
        return HubSpotClient(
            access_token=settings.crm.hubspot_access_token,
            client_secret=settings.crm.webhook_client_secret,
            field_mappings=mappings,
        )

    if crm_type == "salesforce":
        raise NotImplementedError("salesforce CRM client not yet implemented")

    raise ValueError(f"Unknown CRM type: {crm_type}")
