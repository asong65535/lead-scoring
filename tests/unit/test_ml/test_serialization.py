"""Unit tests for model serialization (save/load only — no DB)."""

import numpy as np
import pandas as pd
import pytest

from src.ml.preprocessing import build_preprocessing_pipeline, MVP_FEATURE_NAMES, NUMERIC_FEATURES, BOOLEAN_FEATURES
from src.ml.trainer import train_model
from src.ml.serialization import save_model, load_model, next_version


@pytest.fixture
def trained_result(tmp_path):
    """Train a tiny model for serialization tests."""
    rng = np.random.RandomState(42)
    n = 60
    rows = []
    for _ in range(n):
        converted = rng.random() > 0.5
        row = {name: rng.random() * 10 for name in NUMERIC_FEATURES}
        row.update({name: bool(rng.random() > 0.5) for name in BOOLEAN_FEATURES})
        row["converted"] = converted
        rows.append(row)
    df = pd.DataFrame(rows)
    train_df, test_df = df.iloc[:40], df.iloc[40:]
    pipeline = build_preprocessing_pipeline()
    return train_model(
        train_df[MVP_FEATURE_NAMES], train_df["converted"],
        test_df[MVP_FEATURE_NAMES], test_df["converted"],
        pipeline,
    )


def test_save_creates_joblib_file(trained_result, tmp_path):
    path = save_model(
        trained_result.model, "v1.0",
        trained_result.metrics, trained_result.hyperparameters,
        trained_result.feature_columns, base_dir=tmp_path,
    )
    assert path.exists()
    assert path.suffix == ".joblib"
    assert "v1.0" in path.name


def test_load_returns_pipeline(trained_result, tmp_path):
    path = save_model(
        trained_result.model, "v1.0",
        trained_result.metrics, trained_result.hyperparameters,
        trained_result.feature_columns, base_dir=tmp_path,
    )
    loaded = load_model(path)
    assert hasattr(loaded, "predict_proba")


def test_round_trip_identical_predictions(trained_result, tmp_path):
    rng = np.random.RandomState(99)
    X = pd.DataFrame([{
        **{n: rng.random() * 10 for n in NUMERIC_FEATURES},
        **{b: bool(rng.random() > 0.5) for b in BOOLEAN_FEATURES},
    }])

    path = save_model(
        trained_result.model, "v1.0",
        trained_result.metrics, trained_result.hyperparameters,
        trained_result.feature_columns, base_dir=tmp_path,
    )
    loaded = load_model(path)

    original_proba = trained_result.model.predict_proba(X)
    loaded_proba = loaded.predict_proba(X)
    np.testing.assert_array_equal(original_proba, loaded_proba)


def test_next_version_first():
    assert next_version([]) == "v1.0"


def test_next_version_increments():
    assert next_version(["v1.0", "v1.1", "v1.2"]) == "v1.3"


def test_next_version_handles_unordered():
    assert next_version(["v1.2", "v1.0", "v1.1"]) == "v1.3"


def test_next_version_respects_major():
    assert next_version(["v1.0", "v2.0"]) == "v2.1"
