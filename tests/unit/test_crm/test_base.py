import pytest
from src.services.crm.base import CRMClient


def test_cannot_instantiate_abc():
    with pytest.raises(TypeError):
        CRMClient()


def test_abc_defines_required_methods():
    required = {
        "push_score",
        "fetch_contact",
        "fetch_contacts",
        "validate_webhook",
        "parse_webhook_event",
    }
    abstract_methods = CRMClient.__abstractmethods__
    assert required == abstract_methods
