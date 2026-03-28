"""Tests for PSI-based drift detection."""

import numpy as np
import pytest

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


def test_psi_empty_arrays():
    """PSI should be 0.0 when either array is empty."""
    assert compute_psi([], [1.0, 2.0]) == 0.0
    assert compute_psi([1.0, 2.0], []) == 0.0


def test_psi_is_nonnegative():
    """PSI is always >= 0 regardless of shift direction."""
    rng = np.random.RandomState(42)
    a = rng.normal(10, 2, 500)
    b = rng.normal(5, 2, 500)
    assert compute_psi(a, b) >= 0.0


def test_compute_feature_baselines_numeric_values():
    """Baselines should compute correct mean, std, and preserve raw values."""
    data = [
        {"feat_a": 2.0, "feat_b": True},
        {"feat_a": 4.0, "feat_b": False},
        {"feat_a": 6.0, "feat_b": True},
    ]
    baselines = compute_feature_baselines(
        data, numeric_features=["feat_a"], boolean_features=["feat_b"],
    )
    assert baselines["feat_a"]["mean"] == pytest.approx(4.0)
    assert baselines["feat_a"]["std"] == pytest.approx(np.std([2.0, 4.0, 6.0]))
    assert baselines["feat_a"]["values"] == [2.0, 4.0, 6.0]


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
    assert baselines["feat_b"]["count"] == 4


def test_compute_feature_baselines_skips_none_values():
    """None values in feature dicts should be excluded from baseline computation."""
    data = [
        {"feat_a": 1.0},
        {"feat_a": None},
        {"feat_a": 3.0},
    ]
    baselines = compute_feature_baselines(
        data, numeric_features=["feat_a"], boolean_features=[],
    )
    assert baselines["feat_a"]["mean"] == pytest.approx(2.0)
    assert len(baselines["feat_a"]["values"]) == 2


def test_detect_drift_no_drift():
    rng = np.random.RandomState(42)
    n = 500
    baseline_data = [{"f1": float(v)} for v in rng.normal(5, 2, n)]
    baselines = compute_feature_baselines(baseline_data, numeric_features=["f1"], boolean_features=[])
    recent = [{"f1": float(v)} for v in rng.normal(5, 2, n)]
    result = detect_drift(baselines, recent, numeric_features=["f1"], boolean_features=[])
    assert result.has_significant_drift is False
    assert len(result.drifted_features) == 0
    assert "f1" in result.feature_drift  # PSI was computed even though no drift


def test_detect_drift_with_drift():
    rng = np.random.RandomState(42)
    n = 500
    baseline_data = [{"f1": float(v)} for v in rng.normal(5, 2, n)]
    baselines = compute_feature_baselines(baseline_data, numeric_features=["f1"], boolean_features=[])
    recent = [{"f1": float(v)} for v in rng.normal(15, 2, n)]
    result = detect_drift(baselines, recent, numeric_features=["f1"], boolean_features=[])
    assert result.has_significant_drift is True
    assert "f1" in result.drifted_features
    assert result.feature_drift["f1"] > 0.2


def test_detect_drift_too_few_samples():
    baselines = {"f1": {"mean": 5.0, "std": 2.0, "values": [5.0] * 100}}
    recent = [{"f1": 5.0}]
    result = detect_drift(
        baselines, recent, numeric_features=["f1"], boolean_features=[],
        min_samples=50,
    )
    assert result.has_significant_drift is False
    assert "insufficient" in result.summary.lower()
    assert result.feature_drift == {}  # should not even attempt computation


def test_detect_drift_boolean_feature_shift():
    """Boolean feature with large true-rate shift should be flagged."""
    baselines = {"flag": {"true_rate": 0.8, "count": 200}}
    # 200 recent samples, all False -> true_rate = 0.0, shift = 0.8
    recent = [{"flag": False}] * 200
    result = detect_drift(
        baselines, recent, numeric_features=[], boolean_features=["flag"],
        psi_threshold=0.2,
        min_samples=50,
    )
    assert result.has_significant_drift is True
    assert "flag" in result.drifted_features
    assert result.feature_drift["flag"] == pytest.approx(0.8)


def test_detect_drift_prediction_distribution_computes_stats():
    """When baseline scores and recent scores are provided, prediction drift stats are populated."""
    rng = np.random.RandomState(42)
    n = 500
    baseline_data = [{"f1": float(v)} for v in rng.normal(5, 2, n)]
    baselines = compute_feature_baselines(baseline_data, numeric_features=["f1"], boolean_features=[])
    baselines["_prediction_scores"] = list(rng.uniform(0.2, 0.8, n).astype(float))

    recent = [{"f1": float(v)} for v in rng.normal(5, 2, n)]
    recent_scores = list(rng.uniform(0.5, 1.0, n).astype(float))

    result = detect_drift(
        baselines, recent, numeric_features=["f1"], boolean_features=[],
        recent_scores=recent_scores,
    )
    pred_drift = result.prediction_drift["prediction_drift"]
    assert "baseline_mean" in pred_drift
    assert "recent_mean" in pred_drift
    assert pred_drift["recent_mean"] > pred_drift["baseline_mean"]  # shifted up
    assert pred_drift["psi"] > 0  # distributions differ
