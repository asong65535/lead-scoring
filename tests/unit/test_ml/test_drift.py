"""Tests for PSI-based drift detection."""

import numpy as np

from src.ml.drift import (
    compute_psi,
    compute_feature_baselines,
    detect_drift,
    DriftResult,
)


def test_psi_identical_distributions():
    """PSI should be ~0 for identical distributions."""
    rng = np.random.RandomState(42)
    values = rng.normal(5, 2, 1000)
    psi = compute_psi(values, values, n_bins=10)
    assert psi < 0.01


def test_psi_shifted_distribution():
    """PSI should be high for significantly shifted distributions."""
    rng = np.random.RandomState(42)
    baseline = rng.normal(5, 2, 1000)
    shifted = rng.normal(10, 2, 1000)
    psi = compute_psi(baseline, shifted, n_bins=10)
    assert psi > 0.2


def test_psi_slightly_shifted():
    """Small shift should produce moderate PSI."""
    rng = np.random.RandomState(42)
    baseline = rng.normal(5, 2, 1000)
    shifted = rng.normal(5.5, 2, 1000)
    psi = compute_psi(baseline, shifted, n_bins=10)
    assert 0.0 < psi < 0.2


def test_compute_feature_baselines_numeric():
    """Baselines should include mean, std, and values for numeric features."""
    data = [
        {"feat_a": 1.0, "feat_b": True},
        {"feat_a": 2.0, "feat_b": False},
        {"feat_a": 3.0, "feat_b": True},
    ]
    baselines = compute_feature_baselines(
        data, numeric_features=["feat_a"], boolean_features=["feat_b"],
    )
    assert "feat_a" in baselines
    assert "mean" in baselines["feat_a"]
    assert "std" in baselines["feat_a"]
    assert "values" in baselines["feat_a"]


def test_compute_feature_baselines_boolean():
    """Baselines should include true_rate for boolean features."""
    data = [
        {"feat_a": 1.0, "feat_b": True},
        {"feat_a": 2.0, "feat_b": False},
        {"feat_a": 3.0, "feat_b": True},
        {"feat_a": 4.0, "feat_b": True},
    ]
    baselines = compute_feature_baselines(
        data, numeric_features=["feat_a"], boolean_features=["feat_b"],
    )
    assert baselines["feat_b"]["true_rate"] == 0.75


def test_detect_drift_no_drift():
    rng = np.random.RandomState(42)
    n = 500
    baseline_data = [{"f1": float(v)} for v in rng.normal(5, 2, n)]
    baselines = compute_feature_baselines(baseline_data, numeric_features=["f1"], boolean_features=[])
    recent = [{"f1": float(v)} for v in rng.normal(5, 2, n)]
    result = detect_drift(baselines, recent, numeric_features=["f1"], boolean_features=[])
    assert result.has_significant_drift is False
    assert len(result.drifted_features) == 0


def test_detect_drift_with_drift():
    rng = np.random.RandomState(42)
    n = 500
    baseline_data = [{"f1": float(v)} for v in rng.normal(5, 2, n)]
    baselines = compute_feature_baselines(baseline_data, numeric_features=["f1"], boolean_features=[])
    recent = [{"f1": float(v)} for v in rng.normal(15, 2, n)]
    result = detect_drift(baselines, recent, numeric_features=["f1"], boolean_features=[])
    assert result.has_significant_drift is True
    assert "f1" in result.drifted_features


def test_detect_drift_too_few_samples():
    baselines = {"f1": {"mean": 5.0, "std": 2.0, "values": [5.0] * 100}}
    recent = [{"f1": 5.0}]
    result = detect_drift(
        baselines, recent, numeric_features=["f1"], boolean_features=[],
        min_samples=50,
    )
    assert result.has_significant_drift is False
    assert "insufficient" in result.summary.lower()


def test_detect_drift_prediction_distribution():
    rng = np.random.RandomState(42)
    n = 500
    baseline_data = [{"f1": float(v)} for v in rng.normal(5, 2, n)]
    baselines = compute_feature_baselines(baseline_data, numeric_features=["f1"], boolean_features=[])
    baselines["_prediction_scores"] = list(rng.uniform(0, 1, n).astype(float))
    recent = [{"f1": float(v)} for v in rng.normal(5, 2, n)]
    recent_scores = list(rng.uniform(0, 1, n).astype(float))
    result = detect_drift(
        baselines, recent, numeric_features=["f1"], boolean_features=[],
        recent_scores=recent_scores,
    )
    assert "prediction_drift" in result.prediction_drift or result.prediction_drift == {}
