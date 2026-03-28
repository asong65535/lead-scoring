"""Tests for model comparison logic.

Tests verify the two-gate promotion system: AUC-ROC relative drop gate
and calibration error absolute increase gate.
"""

from config.settings import Settings
from src.ml.comparison import compare_models, ComparisonResult


def test_retrain_settings_defaults():
    s = Settings(
        _env_file=None,
        database={"host": "localhost"},
    )
    assert s.retrain.primary_metric == "auc_roc"
    assert s.retrain.max_relative_drop == 0.05
    assert s.retrain.max_calibration_increase == 0.05
    assert s.retrain.drift_psi_threshold == 0.2
    assert s.retrain.drift_window_days == 7
    assert s.retrain.min_drift_samples == 50
    assert s.retrain.webhook_url is None


def test_promote_when_metrics_improve():
    current = {"auc_roc": 0.85, "calibration_error": 0.05}
    candidate = {"auc_roc": 0.88, "calibration_error": 0.04}
    result = compare_models(current, candidate)
    assert result.should_promote is True


def test_block_when_auc_drops_beyond_threshold():
    """AUC drop of 11.1% (0.90 -> 0.80) exceeds 5% gate."""
    current = {"auc_roc": 0.90, "calibration_error": 0.05}
    candidate = {"auc_roc": 0.80, "calibration_error": 0.05}
    result = compare_models(current, candidate)
    assert result.should_promote is False
    assert "auc_roc" in result.reason.lower()


def test_block_when_calibration_increases_beyond_threshold():
    """Calibration increase of 0.06 (0.03 -> 0.09) exceeds 0.05 gate."""
    current = {"auc_roc": 0.90, "calibration_error": 0.03}
    candidate = {"auc_roc": 0.90, "calibration_error": 0.09}
    result = compare_models(current, candidate)
    assert result.should_promote is False
    assert "calibration" in result.reason.lower()


def test_auc_gate_fires_before_calibration_gate():
    """When both gates would fail, AUC-ROC is checked first."""
    current = {"auc_roc": 0.90, "calibration_error": 0.03}
    candidate = {"auc_roc": 0.70, "calibration_error": 0.20}
    result = compare_models(current, candidate)
    assert result.should_promote is False
    assert "auc_roc" in result.reason.lower()
    assert "calibration" not in result.reason.lower()


def test_calibration_gate_blocks_when_auc_passes():
    """AUC within tolerance but calibration exceeds gate."""
    current = {"auc_roc": 0.90, "calibration_error": 0.03}
    candidate = {"auc_roc": 0.89, "calibration_error": 0.09}
    result = compare_models(current, candidate)
    assert result.should_promote is False
    assert "calibration" in result.reason.lower()


def test_promote_within_tolerance():
    """4% relative AUC drop (0.90 -> 0.864) is under 5% threshold."""
    current = {"auc_roc": 0.90, "calibration_error": 0.05}
    candidate = {"auc_roc": 0.864, "calibration_error": 0.05}
    result = compare_models(current, candidate)
    assert result.should_promote is True


def test_block_just_over_threshold():
    """5.11% relative AUC drop (0.90 -> 0.854) exceeds strict > 5% gate."""
    current = {"auc_roc": 0.90, "calibration_error": 0.05}
    candidate = {"auc_roc": 0.854, "calibration_error": 0.05}
    result = compare_models(current, candidate)
    assert result.should_promote is False


def test_promote_when_no_current_metrics():
    """First-time training always promotes regardless of candidate quality."""
    candidate = {"auc_roc": 0.50, "calibration_error": 0.30}
    result = compare_models(None, candidate)
    assert result.should_promote is True
    assert result.current_metrics is None
    assert result.metric_deltas == {}


def test_metric_deltas_computed_correctly():
    """Deltas are actual absolute and relative differences, not re-derived."""
    current = {"auc_roc": 0.90, "calibration_error": 0.05}
    candidate = {"auc_roc": 0.88, "calibration_error": 0.06}
    result = compare_models(current, candidate)

    auc_delta = result.metric_deltas["auc_roc"]
    assert auc_delta["absolute"] == pytest.approx(-0.02, abs=1e-9)
    assert auc_delta["relative"] == pytest.approx(-0.02 / 0.90, abs=1e-9)

    cal_delta = result.metric_deltas["calibration_error"]
    assert cal_delta["absolute"] == pytest.approx(0.01, abs=1e-9)
    assert cal_delta["relative"] == pytest.approx(0.01 / 0.05, abs=1e-9)


def test_custom_thresholds_widen_gates():
    """With max_relative_drop=0.15, an 11% AUC drop is accepted."""
    current = {"auc_roc": 0.90, "calibration_error": 0.05}
    candidate = {"auc_roc": 0.80, "calibration_error": 0.05}
    result = compare_models(current, candidate, max_relative_drop=0.15)
    assert result.should_promote is True


def test_missing_calibration_error_skips_gate():
    """If neither model reports calibration_error, only AUC gate applies."""
    current = {"auc_roc": 0.90}
    candidate = {"auc_roc": 0.88}
    result = compare_models(current, candidate)
    assert result.should_promote is True


import pytest
