"""Feature registry: loads features.yaml and maps feature names to computation functions."""

from pathlib import Path
from typing import Any, Callable

import yaml

FeatureFunc = Callable  # (Lead, list[Event], datetime) → value

CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "features.yaml"


class FeatureRegistry:
    def __init__(self, config_path: Path = CONFIG_PATH):
        with open(config_path) as f:
            raw = yaml.safe_load(f)
        self._features: list[dict[str, Any]] = raw["features"]
        self._by_name: dict[str, dict[str, Any]] = {f["name"]: f for f in self._features}
        self._functions: dict[str, FeatureFunc] = {}

    def all_features(self) -> list[dict[str, Any]]:
        return list(self._features)

    def register(self, name: str):
        if name not in self._by_name:
            raise KeyError(f"Feature '{name}' not found in features.yaml — cannot register: {name}")

        def decorator(fn: FeatureFunc) -> FeatureFunc:
            self._functions[name] = fn
            return fn
        return decorator

    def computed_features(self) -> set[str]:
        return set(self._functions.keys())

    def defaulted_features(self) -> set[str]:
        return set(self._by_name.keys()) - self.computed_features()

    def get_function(self, name: str) -> FeatureFunc:
        return self._functions[name]

    def get_default(self, name: str) -> Any:
        return self._by_name[name]["default"]

    def get_metadata(self, name: str) -> dict[str, Any]:
        return self._by_name[name]


# Shared singleton — all definition modules register on this instance.
# Lives in registry.py (not __init__.py) to avoid circular imports:
# __init__.py → computer.py → definitions → registry
registry = FeatureRegistry()
