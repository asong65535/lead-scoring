"""Unit tests for feature validation."""

import math
import logging

import pytest
from src.services.features.validation import validate_features
from src.services.features.registry import FeatureRegistry


@pytest.fixture
def registry():
    return FeatureRegistry()


def test_validate_valid_numeric_passes(registry):
    result = validate_features({"days_since_last_visit": 30}, registry)
    assert result["days_since_last_visit"] == 30


def test_validate_nan_replaced_with_default(registry, caplog):
    with caplog.at_level(logging.WARNING):
        result = validate_features({"days_since_last_visit": float("nan")}, registry)
    assert result["days_since_last_visit"] == 365
    assert "days_since_last_visit" in caplog.text


def test_validate_inf_replaced_with_default(registry):
    result = validate_features({"days_since_last_visit": float("inf")}, registry)
    assert result["days_since_last_visit"] == 365


def test_validate_wrong_type_numeric_replaced(registry):
    result = validate_features({"days_since_last_visit": "not_a_number"}, registry)
    assert result["days_since_last_visit"] == 365


def test_validate_valid_boolean_passes(registry):
    result = validate_features({"viewed_pricing": True}, registry)
    assert result["viewed_pricing"] is True


def test_validate_non_bool_replaced_with_default(registry):
    result = validate_features({"viewed_pricing": "yes"}, registry)
    assert result["viewed_pricing"] is False  # default from yaml


def test_validate_valid_categorical_passes(registry):
    result = validate_features({"company_size_bucket": "11-50"}, registry)
    assert result["company_size_bucket"] == "11-50"


def test_validate_invalid_categorical_replaced(registry):
    result = validate_features({"company_size_bucket": "huge"}, registry)
    assert result["company_size_bucket"] == "unknown"  # default from yaml


def test_validate_missing_features_get_defaults(registry):
    """Features not in the input dict get their yaml default."""
    result = validate_features({}, registry)
    assert result["days_since_last_visit"] == 365
    assert result["viewed_pricing"] is False
    assert result["company_size_bucket"] == "unknown"
    assert len(result) == 20  # all features present
