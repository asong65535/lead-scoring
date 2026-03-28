"""Tests for retraining configuration and model comparison."""

from config.settings import Settings


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


from src.ml.comparison import compare_models, ComparisonResult


def test_promote_when_metrics_improve():
    current = {"auc_roc": 0.85, "calibration_error": 0.05}
    candidate = {"auc_roc": 0.88, "calibration_error": 0.04}
    result = compare_models(current, candidate)
    assert result.should_promote is True
    assert "improve" in result.reason.lower() or "better" in result.reason.lower() or "pass" in result.reason.lower()


def test_block_when_auc_drops_beyond_threshold():
    current = {"auc_roc": 0.90, "calibration_error": 0.05}
    candidate = {"auc_roc": 0.80, "calibration_error": 0.05}
    result = compare_models(current, candidate)
    assert result.should_promote is False
    assert "auc_roc" in result.reason.lower()


def test_block_when_calibration_increases_beyond_threshold():
    current = {"auc_roc": 0.90, "calibration_error": 0.03}
    candidate = {"auc_roc": 0.90, "calibration_error": 0.09}
    result = compare_models(current, candidate)
    assert result.should_promote is False
    assert "calibration" in result.reason.lower()


def test_promote_within_tolerance():
    current = {"auc_roc": 0.90, "calibration_error": 0.05}
    candidate = {"auc_roc": 0.864, "calibration_error": 0.05}
    result = compare_models(current, candidate)
    assert result.should_promote is True


def test_block_at_exact_threshold():
    current = {"auc_roc": 0.90, "calibration_error": 0.05}
    candidate = {"auc_roc": 0.854, "calibration_error": 0.05}
    result = compare_models(current, candidate)
    assert result.should_promote is False


def test_promote_when_no_current_metrics():
    candidate = {"auc_roc": 0.75, "calibration_error": 0.10}
    result = compare_models(None, candidate)
    assert result.should_promote is True
    assert result.current_metrics is None


def test_metric_deltas_computed():
    current = {"auc_roc": 0.90, "calibration_error": 0.05}
    candidate = {"auc_roc": 0.88, "calibration_error": 0.06}
    result = compare_models(current, candidate)
    assert "auc_roc" in result.metric_deltas
    delta = result.metric_deltas["auc_roc"]
    assert abs(delta["absolute"] - (-0.02)) < 1e-9
    assert abs(delta["relative"] - (-0.02 / 0.90)) < 1e-9


def test_custom_thresholds():
    current = {"auc_roc": 0.90, "calibration_error": 0.05}
    candidate = {"auc_roc": 0.80, "calibration_error": 0.05}
    result = compare_models(current, candidate, max_relative_drop=0.15)
    assert result.should_promote is True
