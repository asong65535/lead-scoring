import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin


class CRMSyncLog(TimestampMixin, Base):
    __tablename__ = "crm_sync_log"

    lead_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("leads.id", ondelete="RESTRICT"), nullable=False,
    )
    source_system: Mapped[str] = mapped_column(String(20), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="pending",
    )
    error_message: Mapped[str | None] = mapped_column(Text)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    lead: Mapped["Lead"] = relationship(back_populates="sync_logs")

    __table_args__ = (
        CheckConstraint(
            "status IN ('success', 'failed', 'pending')",
            name="ck_crm_sync_log_status",
        ),
        Index("ix_crm_sync_log_lead_id", "lead_id"),
        Index("ix_crm_sync_log_status", "status"),
        Index("ix_crm_sync_log_source_external", "source_system", "external_id"),
    )
