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
