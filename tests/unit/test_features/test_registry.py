"""Unit tests for FeatureRegistry."""

import pytest
from src.services.features.registry import FeatureRegistry


@pytest.fixture
def registry():
    return FeatureRegistry()


def test_registry_loads_all_features_from_yaml(registry):
    """All 20 features from features.yaml must be known to the registry."""
    assert len(registry.all_features()) == 20


def test_registry_every_feature_has_category(registry):
    for feat in registry.all_features():
        assert feat["category"] in (
            "recency", "frequency", "intensity", "intent", "firmographic", "engagement",
        ), f"{feat['name']} missing valid category"


def test_registry_computed_and_defaulted_union_equals_all(registry):
    """Every feature is either computed or defaulted — none missing."""
    computed = registry.computed_features()
    defaulted = registry.defaulted_features()
    all_names = {f["name"] for f in registry.all_features()}
    assert computed | defaulted == all_names
    assert computed & defaulted == set()  # no overlap


def test_registry_register_decorator(registry):
    """A registered function should appear in computed_features."""
    @registry.register("days_since_last_visit")
    def dummy(lead, events, as_of_date):
        return 42

    assert "days_since_last_visit" in registry.computed_features()


def test_registry_register_unknown_feature_raises(registry):
    with pytest.raises(KeyError, match="not_a_real_feature"):
        @registry.register("not_a_real_feature")
        def dummy(lead, events, as_of_date):
            return 0


def test_registry_get_function(registry):
    @registry.register("days_since_last_visit")
    def my_func(lead, events, as_of_date):
        return 99

    fn = registry.get_function("days_since_last_visit")
    assert fn(None, [], None) == 99


def test_registry_get_default(registry):
    default = registry.get_default("days_since_last_visit")
    assert default == 365


def test_registry_get_metadata(registry):
    meta = registry.get_metadata("days_since_last_visit")
    assert meta["type"] == "numeric"
    assert meta["category"] == "recency"
