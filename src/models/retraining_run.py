from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin


class RetrainingRun(TimestampMixin, Base):
    __tablename__ = "retraining_runs"

    run_status: Mapped[str] = mapped_column(String(20), nullable=False)
    candidate_version: Mapped[str] = mapped_column(String(20), nullable=False)
    active_version_before: Mapped[str | None] = mapped_column(String(20))
    promoted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    current_metrics: Mapped[dict | None] = mapped_column(JSONB)
    candidate_metrics: Mapped[dict | None] = mapped_column(JSONB)
    metric_deltas: Mapped[dict | None] = mapped_column(JSONB)
    comparison_reason: Mapped[str | None] = mapped_column(Text)
    drift_result: Mapped[dict | None] = mapped_column(JSONB)
    feature_baselines: Mapped[dict | None] = mapped_column(JSONB)
    training_data_stats: Mapped[dict | None] = mapped_column(JSONB)
    hyperparameters: Mapped[dict | None] = mapped_column(JSONB)
    triggered_by: Mapped[str] = mapped_column(String(20), nullable=False)
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "run_status IN ('success', 'blocked', 'failed')",
            name="ck_retraining_runs_status",
        ),
        Index("ix_retraining_runs_status", "run_status"),
        Index("ix_retraining_runs_started_at", "started_at"),
    )
