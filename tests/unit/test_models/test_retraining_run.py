"""Tests for RetrainingRun ORM model.

Verifies column contracts (types, nullability, constraints) that matter
for correctness — not just existence.
"""

import sqlalchemy as sa

from src.models.retraining_run import RetrainingRun


def _col(name: str) -> sa.Column:
    return RetrainingRun.__table__.c[name]


def test_retraining_run_tablename():
    assert RetrainingRun.__tablename__ == "retraining_runs"


def test_run_status_is_not_nullable():
    assert _col("run_status").nullable is False


def test_run_status_check_constraint_allows_expected_values():
    """The CHECK constraint should restrict to success/blocked/failed."""
    constraints = [
        c for c in RetrainingRun.__table__.constraints
        if isinstance(c, sa.CheckConstraint) and c.name and "status" in c.name
    ]
    assert len(constraints) == 1
    # Verify the constraint text contains all three valid values
    constraint_text = str(constraints[0].sqltext)
    for value in ("success", "blocked", "failed"):
        assert value in constraint_text


def test_candidate_version_is_not_nullable():
    assert _col("candidate_version").nullable is False


def test_promoted_is_not_nullable_boolean():
    assert _col("promoted").nullable is False
    assert isinstance(_col("promoted").type, sa.Boolean)


def test_jsonb_columns_are_nullable():
    """JSONB columns should be nullable (not all runs produce all data)."""
    jsonb_cols = [
        "current_metrics", "candidate_metrics", "metric_deltas",
        "drift_result", "feature_baselines", "training_data_stats",
        "hyperparameters",
    ]
    for name in jsonb_cols:
        assert _col(name).nullable is True, f"{name} should be nullable"


def test_started_at_is_not_nullable():
    assert _col("started_at").nullable is False


def test_completed_at_is_nullable():
    """completed_at is null during the run, set on completion."""
    assert _col("completed_at").nullable is True


def test_error_message_is_nullable_text():
    col = _col("error_message")
    assert col.nullable is True
    assert isinstance(col.type, sa.Text)


def test_indexes_exist_on_status_and_started_at():
    index_names = {idx.name for idx in RetrainingRun.__table__.indexes}
    assert "ix_retraining_runs_status" in index_names
    assert "ix_retraining_runs_started_at" in index_names
