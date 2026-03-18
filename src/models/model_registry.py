from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin


class ModelRegistry(TimestampMixin, Base):
    __tablename__ = "model_registry"

    version: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    artifact_path: Mapped[str] = mapped_column(String(500), nullable=False)
    metrics: Mapped[dict | None] = mapped_column(JSONB)
    hyperparameters: Mapped[dict | None] = mapped_column(JSONB)
    feature_columns: Mapped[list | None] = mapped_column(JSONB)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    trained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index(
            "ix_model_registry_active",
            "is_active",
            postgresql_where=(is_active == True),  # noqa: E712
        ),
    )
