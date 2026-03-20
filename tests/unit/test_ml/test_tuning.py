"""Unit tests for hyperparameter tuning."""

import numpy as np
import pandas as pd
import pytest

from src.ml.preprocessing import build_preprocessing_pipeline, NUMERIC_FEATURES, BOOLEAN_FEATURES, MVP_FEATURE_NAMES
from src.ml.tuning import tune_hyperparameters, DEFAULT_PARAM_GRID


@pytest.fixture
def small_data():
    """Minimal dataset for tuning tests (keep it fast)."""
    rng = np.random.RandomState(42)
    n = 100
    rows = []
    for _ in range(n):
        converted = rng.random() > 0.5
        row = {}
        for name in NUMERIC_FEATURES:
            row[name] = rng.random() * 10 + (3.0 if converted else 0.0)
        for name in BOOLEAN_FEATURES:
            row[name] = bool(rng.random() > (0.3 if converted else 0.7))
        row["converted"] = converted
        rows.append(row)
    df = pd.DataFrame(rows)
    return df[MVP_FEATURE_NAMES], df["converted"]


def test_tune_returns_dict(small_data):
    X, y = small_data
    pipeline = build_preprocessing_pipeline()
    tiny_grid = {"n_estimators": [10], "max_depth": [3]}
    result = tune_hyperparameters(X, y, pipeline, param_grid=tiny_grid, cv_folds=2)
    assert isinstance(result, dict)
    assert "n_estimators" in result
    assert "max_depth" in result


def test_tune_respects_custom_grid(small_data):
    X, y = small_data
    pipeline = build_preprocessing_pipeline()
    tiny_grid = {"n_estimators": [10, 20], "max_depth": [2]}
    result = tune_hyperparameters(X, y, pipeline, param_grid=tiny_grid, cv_folds=2)
    assert result["n_estimators"] in [10, 20]
    assert result["max_depth"] == 2


def test_default_param_grid_has_expected_keys():
    assert "n_estimators" in DEFAULT_PARAM_GRID
    assert "max_depth" in DEFAULT_PARAM_GRID
    assert "learning_rate" in DEFAULT_PARAM_GRID
    assert "subsample" in DEFAULT_PARAM_GRID


def test_default_param_grid_yields_81_combos():
    combos = 1
    for values in DEFAULT_PARAM_GRID.values():
        combos *= len(values)
    assert combos == 81
