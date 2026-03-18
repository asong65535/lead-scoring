import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin


class Prediction(TimestampMixin, Base):
    __tablename__ = "predictions"

    lead_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("leads.id", ondelete="RESTRICT"), nullable=False,
    )
    score: Mapped[float] = mapped_column(Float, nullable=False)
    bucket: Mapped[str] = mapped_column(String(10), nullable=False)
    model_version: Mapped[str] = mapped_column(String(20), nullable=False)
    feature_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    top_factors: Mapped[dict | None] = mapped_column(JSONB)
    scored_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    lead: Mapped["Lead"] = relationship(back_populates="predictions")

    __table_args__ = (
        CheckConstraint("bucket IN ('A', 'B', 'C', 'D')", name="ck_predictions_bucket"),
        Index("ix_predictions_lead_id", "lead_id"),
        Index("ix_predictions_scored_at", "scored_at"),
        Index("ix_predictions_lead_id_scored_at", "lead_id", text("scored_at DESC")),
        Index("ix_predictions_model_version", "model_version"),
    )
