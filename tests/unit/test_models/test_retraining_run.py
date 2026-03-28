"""Tests for RetrainingRun ORM model."""

from src.models.retraining_run import RetrainingRun


def test_retraining_run_tablename():
    assert RetrainingRun.__tablename__ == "retraining_runs"


def test_retraining_run_has_expected_columns():
    col_names = {c.name for c in RetrainingRun.__table__.columns}
    expected = {
        "id", "created_at", "updated_at",
        "run_status", "candidate_version", "active_version_before",
        "promoted", "current_metrics", "candidate_metrics",
        "metric_deltas", "comparison_reason", "drift_result",
        "feature_baselines", "training_data_stats", "hyperparameters",
        "triggered_by", "duration_seconds", "error_message",
        "started_at", "completed_at",
    }
    assert expected.issubset(col_names)


def test_retraining_run_status_check_constraint():
    constraints = [c for c in RetrainingRun.__table__.constraints
                   if hasattr(c, "name") and c.name and "status" in c.name]
    assert len(constraints) == 1
