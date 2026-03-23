import pytest
from unittest.mock import MagicMock
from src.services.crm.factory import get_crm_client
from src.services.crm.hubspot import HubSpotClient


def test_factory_returns_none_for_type_none():
    settings = MagicMock()
    settings.crm.type = "none"
    result = get_crm_client(settings)
    assert result is None


def test_factory_returns_hubspot_client():
    settings = MagicMock()
    settings.crm.type = "hubspot"
    settings.crm.hubspot_access_token = "test-token"
    settings.crm.webhook_client_secret = "test-secret"
    settings.crm_mappings = {
        "hubspot": {
            "output_fields": {"score": "lead_score", "bucket": "lead_score_bucket"},
        },
    }
    result = get_crm_client(settings)
    assert isinstance(result, HubSpotClient)


def test_factory_raises_for_salesforce():
    settings = MagicMock()
    settings.crm.type = "salesforce"
    with pytest.raises(NotImplementedError, match="salesforce"):
        get_crm_client(settings)


def test_factory_raises_for_unknown_type():
    settings = MagicMock()
    settings.crm.type = "unknown"
    with pytest.raises(ValueError, match="unknown"):
        get_crm_client(settings)
