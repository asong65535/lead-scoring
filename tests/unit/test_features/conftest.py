"""Shared helpers for feature unit tests."""

from types import SimpleNamespace


def make_test_lead(**kw):
    """Create a plain namespace that duck-types a Lead. Sets required fields."""
    defaults = {"external_id": "test-001", "source_system": "kaggle"}
    defaults.update(kw)
    return SimpleNamespace(**defaults)


def make_test_event(**kw):
    """Create a plain namespace that duck-types an Event."""
    return SimpleNamespace(**kw)
