"""Tests for retrain script logic (no DB required).

These tests verify the orchestration logic in execute_retrain:
- correct promotion decisions based on comparison results
- force flag overrides comparison
- dry_run prevents side effects
- drift detection results are passed through

Heavy integration is covered by tests/integration/test_retrain_pipeline.py.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

import pandas as pd

from src.ml.comparison import ComparisonResult
from src.ml.drift import DriftResult


def _make_train_result(metrics=None):
    from src.ml.trainer import TrainResult
    return TrainResult(
        model=MagicMock(),
        metrics=metrics or {"auc_roc": 0.90, "calibration_error": 0.04},
        feature_importance={"feat_a": 0.5},
        hyperparameters={"n_estimators": 200},
        feature_columns=["feat_a"],
    )


def _mock_settings():
    s = MagicMock()
    s.retrain.webhook_url = None
    s.retrain.primary_metric = "auc_roc"
    s.retrain.max_relative_drop = 0.05
    s.retrain.max_calibration_increase = 0.05
    s.retrain.drift_psi_threshold = 0.2
    s.retrain.drift_window_days = 7
    s.retrain.min_drift_samples = 50
    return s


# Minimal patches that replace only I/O boundaries (DB, filesystem, network),
# letting the real orchestration logic run.
def _common_patches(active_info=None, train_result=None):
    train_result = train_result or _make_train_result()
    mock_train = pd.DataFrame({"feat_a": [1, 2, 3], "converted": [True, False, True]})
    mock_test = pd.DataFrame({"feat_a": [4], "converted": [False]})

    return {
        "scripts.retrain.get_active_model_info": AsyncMock(return_value=active_info),
        "scripts.retrain.run_drift_detection": AsyncMock(return_value=None),
        "scripts.retrain.build_training_dataset": AsyncMock(return_value=(mock_train, mock_test)),
        "scripts.retrain.build_preprocessing_pipeline": MagicMock(return_value=MagicMock()),
        "scripts.retrain.train_model": MagicMock(return_value=train_result),
        "scripts.retrain.save_model": MagicMock(return_value="models/v1.0.joblib"),
        "scripts.retrain.register_model": AsyncMock(return_value="fake-uuid"),
        "scripts.retrain.get_existing_versions": AsyncMock(return_value=[]),
        "scripts.retrain.trigger_hot_reload": AsyncMock(),
        "scripts.retrain.send_alert": AsyncMock(),
        "scripts.retrain.record_run": AsyncMock(),
        "scripts.retrain.MVP_FEATURE_NAMES": ["feat_a"],
        "scripts.retrain.NUMERIC_FEATURES": ["feat_a"],
        "scripts.retrain.BOOLEAN_FEATURES": [],
    }


def test_determine_triggered_by_flags():
    from scripts.retrain import determine_triggered_by
    assert determine_triggered_by(force=True) == "force"
    assert determine_triggered_by(force=False) == "manual"


@pytest.mark.asyncio
async def test_first_run_promotes_via_real_comparison():
    """When no active model exists, compare_models (real) returns should_promote=True."""
    from scripts.retrain import execute_retrain

    patches = _common_patches(active_info=None)
    # Do NOT mock compare_models — let it run for real with current_metrics=None
    with _apply_patches(patches):
        summary = await execute_retrain(
            engine=AsyncMock(),
            tune=False,
            force=False,
            dry_run=False,
            settings=_mock_settings(),
        )

    assert summary["promoted"] is True
    assert summary["run_status"] == "success"
    # compare_models(None, candidate) always promotes
    assert summary["comparison"].should_promote is True
    assert summary["comparison"].current_metrics is None


@pytest.mark.asyncio
async def test_force_overrides_blocked_comparison():
    """force=True should promote even when comparison blocks."""
    from scripts.retrain import execute_retrain

    active_info = {"version": "v1.0", "metrics": {"auc_roc": 0.95, "calibration_error": 0.02}, "artifact_path": "models/v1.0.joblib"}
    bad_metrics = {"auc_roc": 0.70, "calibration_error": 0.10}
    train_result = _make_train_result(metrics=bad_metrics)

    patches = _common_patches(active_info=active_info, train_result=train_result)
    # Let compare_models run for real — it should return should_promote=False
    with _apply_patches(patches):
        summary = await execute_retrain(
            engine=AsyncMock(),
            tune=False,
            force=True,
            dry_run=False,
            settings=_mock_settings(),
        )

    # Real comparison says no, but force overrides
    assert summary["comparison"].should_promote is False
    assert summary["promoted"] is True
    assert summary["run_status"] == "success"


@pytest.mark.asyncio
async def test_blocked_when_metrics_degrade():
    """When candidate metrics are worse, the model is not promoted."""
    from scripts.retrain import execute_retrain

    active_info = {"version": "v1.0", "metrics": {"auc_roc": 0.95, "calibration_error": 0.02}, "artifact_path": "models/v1.0.joblib"}
    bad_metrics = {"auc_roc": 0.70, "calibration_error": 0.10}
    train_result = _make_train_result(metrics=bad_metrics)

    patches = _common_patches(active_info=active_info, train_result=train_result)
    with _apply_patches(patches):
        summary = await execute_retrain(
            engine=AsyncMock(),
            tune=False,
            force=False,
            dry_run=False,
            settings=_mock_settings(),
        )

    assert summary["promoted"] is False
    assert summary["run_status"] == "blocked"
    assert summary["comparison"].should_promote is False


@pytest.mark.asyncio
async def test_dry_run_never_promotes():
    """dry_run=True trains and compares but does not promote or register as active."""
    from scripts.retrain import execute_retrain

    patches = _common_patches(active_info=None)
    with _apply_patches(patches) as mocks:
        summary = await execute_retrain(
            engine=AsyncMock(),
            tune=False,
            force=False,
            dry_run=True,
            settings=_mock_settings(),
        )

    assert summary["dry_run"] is True
    assert summary["promoted"] is False
    # save_model and register_model should NOT be called in dry_run
    mocks["scripts.retrain.save_model"].assert_not_called()
    mocks["scripts.retrain.register_model"].assert_not_called()
    # But record_run IS called (to persist the dry run)
    mocks["scripts.retrain.record_run"].assert_called_once()


@pytest.mark.asyncio
async def test_record_run_called_with_correct_status():
    """record_run receives the actual run_status matching the promotion decision."""
    from scripts.retrain import execute_retrain

    active_info = {"version": "v1.0", "metrics": {"auc_roc": 0.95, "calibration_error": 0.02}, "artifact_path": "models/v1.0.joblib"}
    bad_metrics = {"auc_roc": 0.70, "calibration_error": 0.10}
    train_result = _make_train_result(metrics=bad_metrics)

    patches = _common_patches(active_info=active_info, train_result=train_result)
    with _apply_patches(patches) as mocks:
        await execute_retrain(
            engine=AsyncMock(),
            tune=False,
            force=False,
            dry_run=False,
            settings=_mock_settings(),
        )

    call_kwargs = mocks["scripts.retrain.record_run"].call_args[1]
    assert call_kwargs["run_status"] == "blocked"
    assert call_kwargs["promoted"] is False
    assert call_kwargs["candidate_metrics"] == bad_metrics


import contextlib


@contextlib.contextmanager
def _apply_patches(patch_dict):
    """Apply a dict of patches and yield the mock objects for assertion."""
    mocks = {}
    stack = contextlib.ExitStack()
    for target, mock_obj in patch_dict.items():
        if isinstance(mock_obj, (list, str, int, float, dict)):
            m = stack.enter_context(patch(target, mock_obj))
        else:
            m = stack.enter_context(patch(target, mock_obj))
            mocks[target] = mock_obj
    with stack:
        yield mocks
