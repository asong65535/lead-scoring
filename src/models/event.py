import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin

VALID_EVENT_TYPES = ("page_view", "email_open", "email_click", "form_submission", "email_unsubscribe")


class Event(TimestampMixin, Base):
    __tablename__ = "events"

    lead_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    event_name: Mapped[str | None] = mapped_column(String(100))
    properties: Mapped[dict | None] = mapped_column(JSONB)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )

    lead: Mapped["Lead"] = relationship(back_populates="events")

    __table_args__ = (
        CheckConstraint(
            f"event_type IN ({', '.join(repr(t) for t in VALID_EVENT_TYPES)})",
            name="ck_events_event_type",
        ),
        Index("ix_events_lead_id_occurred_at", "lead_id", "occurred_at"),
        Index("ix_events_event_type", "event_type"),
    )
