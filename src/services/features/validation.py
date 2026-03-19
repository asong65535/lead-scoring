"""Validate feature values against features.yaml metadata."""

import logging
import math
from typing import Any

from src.services.features.registry import FeatureRegistry

logger = logging.getLogger(__name__)


def _is_valid_numeric(value: Any) -> bool:
    if not isinstance(value, (int, float)):
        return False
    if math.isnan(value) or math.isinf(value):
        return False
    return True


def _is_valid_boolean(value: Any) -> bool:
    return isinstance(value, bool)


def _is_valid_categorical(value: Any, categories: list[str]) -> bool:
    return value in categories


def validate_features(
    raw: dict[str, Any],
    registry: FeatureRegistry,
    lead_id: str | None = None,
) -> dict[str, Any]:
    """Validate and fill feature dict. Returns dict with all 20 features, type-correct."""
    result = {}
    for feat in registry.all_features():
        name = feat["name"]
        ftype = feat["type"]
        default = feat["default"]
        value = raw.get(name)

        valid = False
        if value is not None:
            if ftype == "numeric":
                valid = _is_valid_numeric(value)
            elif ftype == "boolean":
                valid = _is_valid_boolean(value)
            elif ftype == "categorical":
                valid = _is_valid_categorical(value, feat.get("categories", []))

        if valid:
            result[name] = value
        else:
            if value is not None:
                logger.warning(
                    "Invalid feature value replaced with default: "
                    "lead_id=%s feature=%s value=%r default=%r",
                    lead_id, name, value, default,
                )
            result[name] = default

    return result
