import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin


class Lead(TimestampMixin, Base):
    __tablename__ = "leads"

    external_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    source_system: Mapped[str] = mapped_column(String(20), nullable=False)
    lead_origin: Mapped[str | None] = mapped_column(String(50))
    lead_source: Mapped[str | None] = mapped_column(String(100))
    country: Mapped[str | None] = mapped_column(String(100))
    city: Mapped[str | None] = mapped_column(String(100))
    current_occupation: Mapped[str | None] = mapped_column(String(100))
    specialization: Mapped[str | None] = mapped_column(String(100))
    do_not_email: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    do_not_call: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    total_visits: Mapped[float | None] = mapped_column(Float)
    total_time_spent: Mapped[float | None] = mapped_column(Float)
    page_views_per_visit: Mapped[float | None] = mapped_column(Float)
    last_activity: Mapped[str | None] = mapped_column(String(100))
    tags: Mapped[str | None] = mapped_column(String(200))
    converted: Mapped[bool | None] = mapped_column(Boolean)
    converted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships (defined here, back_populates set in child models)
    predictions: Mapped[list["Prediction"]] = relationship(back_populates="lead")
    sync_logs: Mapped[list["CRMSyncLog"]] = relationship(back_populates="lead")
    events: Mapped[list["Event"]] = relationship(back_populates="lead", passive_deletes=True)

    __table_args__ = (
        Index("ix_leads_source_system", "source_system"),
        Index("ix_leads_converted", "converted"),
    )
