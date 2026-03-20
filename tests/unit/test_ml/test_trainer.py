"""Unit tests for model trainer."""

import numpy as np
import pandas as pd
import pytest

from src.ml.preprocessing import build_preprocessing_pipeline, MVP_FEATURE_NAMES, NUMERIC_FEATURES, BOOLEAN_FEATURES
from src.ml.trainer import train_model, TrainResult, DEFAULT_HYPERPARAMETERS


@pytest.fixture
def synthetic_data():
    """Small synthetic dataset with separable classes."""
    rng = np.random.RandomState(42)
    n = 200
    rows = []
    for _ in range(n):
        converted = rng.random() > 0.6
        row = {}
        for name in NUMERIC_FEATURES:
            row[name] = rng.random() * 10 + (5.0 if converted else 0.0)
        for name in BOOLEAN_FEATURES:
            row[name] = bool(rng.random() > (0.3 if converted else 0.7))
        row["converted"] = converted
        rows.append(row)
    df = pd.DataFrame(rows)
    train_df = df.iloc[:160].reset_index(drop=True)
    test_df = df.iloc[160:].reset_index(drop=True)
    return train_df, test_df


def test_train_returns_train_result(synthetic_data):
    train_df, test_df = synthetic_data
    X_train = train_df[MVP_FEATURE_NAMES]
    y_train = train_df["converted"]
    X_test = test_df[MVP_FEATURE_NAMES]
    y_test = test_df["converted"]
    pipeline = build_preprocessing_pipeline()
    result = train_model(X_train, y_train, X_test, y_test, pipeline)
    assert isinstance(result, TrainResult)


def test_train_result_has_all_metrics(synthetic_data):
    train_df, test_df = synthetic_data
    X_train = train_df[MVP_FEATURE_NAMES]
    y_train = train_df["converted"]
    X_test = test_df[MVP_FEATURE_NAMES]
    y_test = test_df["converted"]
    pipeline = build_preprocessing_pipeline()
    result = train_model(X_train, y_train, X_test, y_test, pipeline)
    for key in ("auc_roc", "precision", "recall", "f1", "log_loss", "calibration_error"):
        assert key in result.metrics, f"Missing metric: {key}"


def test_metrics_in_valid_ranges(synthetic_data):
    train_df, test_df = synthetic_data
    X_train = train_df[MVP_FEATURE_NAMES]
    y_train = train_df["converted"]
    X_test = test_df[MVP_FEATURE_NAMES]
    y_test = test_df["converted"]
    pipeline = build_preprocessing_pipeline()
    result = train_model(X_train, y_train, X_test, y_test, pipeline)
    assert 0.0 <= result.metrics["auc_roc"] <= 1.0
    assert 0.0 <= result.metrics["precision"] <= 1.0
    assert 0.0 <= result.metrics["recall"] <= 1.0
    assert 0.0 <= result.metrics["f1"] <= 1.0
    assert result.metrics["log_loss"] >= 0.0
    assert 0.0 <= result.metrics["calibration_error"] <= 1.0


def test_feature_importance_has_all_features(synthetic_data):
    train_df, test_df = synthetic_data
    X_train = train_df[MVP_FEATURE_NAMES]
    y_train = train_df["converted"]
    X_test = test_df[MVP_FEATURE_NAMES]
    y_test = test_df["converted"]
    pipeline = build_preprocessing_pipeline()
    result = train_model(X_train, y_train, X_test, y_test, pipeline)
    assert set(result.feature_importance.keys()) == set(MVP_FEATURE_NAMES)


def test_feature_columns_matches_mvp(synthetic_data):
    train_df, test_df = synthetic_data
    X_train = train_df[MVP_FEATURE_NAMES]
    y_train = train_df["converted"]
    X_test = test_df[MVP_FEATURE_NAMES]
    y_test = test_df["converted"]
    pipeline = build_preprocessing_pipeline()
    result = train_model(X_train, y_train, X_test, y_test, pipeline)
    assert result.feature_columns == MVP_FEATURE_NAMES


def test_custom_hyperparameters_used(synthetic_data):
    train_df, test_df = synthetic_data
    X_train = train_df[MVP_FEATURE_NAMES]
    y_train = train_df["converted"]
    X_test = test_df[MVP_FEATURE_NAMES]
    y_test = test_df["converted"]
    pipeline = build_preprocessing_pipeline()
    custom = {"n_estimators": 50, "max_depth": 3}
    result = train_model(X_train, y_train, X_test, y_test, pipeline, hyperparameters=custom)
    assert result.hyperparameters["n_estimators"] == 50
    assert result.hyperparameters["max_depth"] == 3


def test_model_can_predict(synthetic_data):
    train_df, test_df = synthetic_data
    X_train = train_df[MVP_FEATURE_NAMES]
    y_train = train_df["converted"]
    X_test = test_df[MVP_FEATURE_NAMES]
    y_test = test_df["converted"]
    pipeline = build_preprocessing_pipeline()
    result = train_model(X_train, y_train, X_test, y_test, pipeline)
    probas = result.model.predict_proba(X_test)
    assert probas.shape == (len(X_test), 2)
    assert all(0.0 <= p <= 1.0 for p in probas[:, 1])


def test_default_hyperparameters_are_sensible():
    assert DEFAULT_HYPERPARAMETERS["n_estimators"] == 200
    assert DEFAULT_HYPERPARAMETERS["max_depth"] == 6
    assert DEFAULT_HYPERPARAMETERS["random_state"] == 42


def test_scale_pos_weight_computed_correctly(synthetic_data):
    train_df, test_df = synthetic_data
    X_train = train_df[MVP_FEATURE_NAMES]
    y_train = train_df["converted"]
    X_test = test_df[MVP_FEATURE_NAMES]
    y_test = test_df["converted"]
    pipeline = build_preprocessing_pipeline()
    result = train_model(X_train, y_train, X_test, y_test, pipeline)

    n_neg = int((y_train == False).sum())
    n_pos = int((y_train == True).sum())
    expected_weight = n_neg / n_pos

    assert result.hyperparameters["scale_pos_weight"] == pytest.approx(expected_weight)
