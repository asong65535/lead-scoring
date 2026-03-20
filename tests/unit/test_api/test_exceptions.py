"""Tests for custom API exceptions."""

from uuid import uuid4

from src.api.exceptions import (
    FeatureComputationError,
    LeadNotFoundError,
    ModelNotLoadedError,
)


def test_lead_not_found_error_stores_lead_id():
    lead_id = uuid4()
    exc = LeadNotFoundError(lead_id)
    assert exc.lead_id == lead_id
    assert str(lead_id) in str(exc)


def test_model_not_loaded_error_message():
    exc = ModelNotLoadedError()
    assert "not available" in str(exc).lower() or "not loaded" in str(exc).lower()


def test_feature_computation_error_stores_detail():
    exc = FeatureComputationError("missing required features")
    assert exc.detail == "missing required features"
