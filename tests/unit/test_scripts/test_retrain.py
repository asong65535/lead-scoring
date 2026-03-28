"""Tests for retrain script logic (no DB required)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from src.ml.comparison import ComparisonResult


def _make_train_result(metrics=None):
    """Helper to create a mock TrainResult."""
    from src.ml.trainer import TrainResult
    result = TrainResult(
        model=MagicMock(),
        metrics=metrics or {"auc_roc": 0.90, "calibration_error": 0.04},
        feature_importance={"feat_a": 0.5},
        hyperparameters={"n_estimators": 200},
        feature_columns=["feat_a"],
    )
    return result


def test_determine_triggered_by_flags():
    from scripts.retrain import determine_triggered_by
    assert determine_triggered_by(force=True) == "force"
    assert determine_triggered_by(force=False) == "manual"


@pytest.mark.asyncio
async def test_retrain_first_run_promotes():
    """When no active model exists, retrain should always promote."""
    from scripts.retrain import execute_retrain

    mock_engine = AsyncMock()
    train_result = _make_train_result()

    import pandas as pd
    mock_train = pd.DataFrame({"feat_a": [1, 2], "converted": [True, False]})
    mock_test = pd.DataFrame({"feat_a": [3], "converted": [True]})

    mock_settings = MagicMock()
    mock_settings.retrain.webhook_url = None
    mock_settings.retrain.primary_metric = "auc_roc"
    mock_settings.retrain.max_relative_drop = 0.05
    mock_settings.retrain.max_calibration_increase = 0.05
    mock_settings.retrain.drift_psi_threshold = 0.2
    mock_settings.retrain.drift_window_days = 7
    mock_settings.retrain.min_drift_samples = 50

    with (
        patch("scripts.retrain.get_active_model_info", new_callable=AsyncMock, return_value=None),
        patch("scripts.retrain.run_drift_detection", new_callable=AsyncMock, return_value=None),
        patch("scripts.retrain.build_training_dataset", new_callable=AsyncMock, return_value=(mock_train, mock_test)),
        patch("scripts.retrain.build_preprocessing_pipeline") as mock_preproc,
        patch("scripts.retrain.train_model", return_value=train_result),
        patch("scripts.retrain.compare_models") as mock_compare,
        patch("scripts.retrain.save_model", return_value="models/v1.0.joblib"),
        patch("scripts.retrain.register_model", new_callable=AsyncMock, return_value="fake-uuid"),
        patch("scripts.retrain.get_existing_versions", new_callable=AsyncMock, return_value=[]),
        patch("scripts.retrain.next_version", return_value="v1.0"),
        patch("scripts.retrain.trigger_hot_reload", new_callable=AsyncMock),
        patch("scripts.retrain.send_alert", new_callable=AsyncMock),
        patch("scripts.retrain.record_run", new_callable=AsyncMock),
        patch("scripts.retrain.compute_feature_baselines", return_value={}),
        patch("scripts.retrain.compute_training_data_stats", return_value={}),
        patch("scripts.retrain.MVP_FEATURE_NAMES", ["feat_a"]),
        patch("scripts.retrain.NUMERIC_FEATURES", ["feat_a"]),
        patch("scripts.retrain.BOOLEAN_FEATURES", []),
    ):
        mock_compare.return_value = ComparisonResult(
            should_promote=True,
            reason="No active model",
            current_metrics=None,
            candidate_metrics=train_result.metrics,
            metric_deltas={},
        )
        mock_preproc.return_value = MagicMock()

        summary = await execute_retrain(
            engine=mock_engine,
            tune=False,
            force=False,
            dry_run=False,
            settings=mock_settings,
        )

    assert summary["promoted"] is True
    assert summary["candidate_version"] == "v1.0"
