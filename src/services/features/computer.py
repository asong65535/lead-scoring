"""Feature computation orchestrator."""

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, AsyncEngine
from sqlalchemy.orm import selectinload

from src.models.event import Event
from src.models.lead import Lead
from src.services.features.registry import registry
from src.services.features.definitions import *  # noqa: F401,F403 — trigger registrations
from src.services.features.validation import validate_features


class FeatureComputer:
    def __init__(self, engine: AsyncEngine):
        self._engine = engine
        self._registry = registry
        self._session_factory = async_sessionmaker(
            bind=engine, class_=AsyncSession, expire_on_commit=False,
        )

    def _compute_for_lead(
        self, lead: Lead, events: list[Event], as_of_date: datetime,
    ) -> dict[str, Any]:
        """Compute features for a single lead (no DB access)."""
        filtered = [e for e in events if e.occurred_at < as_of_date]

        events_by_type: dict[str, list[Event]] = defaultdict(list)
        for e in filtered:
            events_by_type[e.event_type].append(e)
        events_by_type["_all"] = filtered

        raw = {}
        for name in self._registry.computed_features():
            fn = self._registry.get_function(name)
            raw[name] = fn(lead, events_by_type, as_of_date)

        validated = validate_features(raw, self._registry, lead_id=str(lead.id))
        validated["lead_id"] = lead.id
        validated["computed_at"] = datetime.now(timezone.utc)
        return validated

    async def compute(
        self, lead_id: UUID, as_of_date: datetime | None = None,
    ) -> dict[str, Any]:
        as_of_date = as_of_date or datetime.now(timezone.utc)

        async with self._session_factory() as session:
            result = await session.execute(
                select(Lead)
                .options(selectinload(Lead.events))
                .where(Lead.id == lead_id)
            )
            lead = result.scalar_one()

        # lead.events is safe post-session: selectinload populates it eagerly,
        # and expire_on_commit=False prevents expiration on close.
        return self._compute_for_lead(lead, lead.events, as_of_date)

    async def compute_batch(
        self,
        lead_ids: list[UUID],
        as_of_dates: dict[UUID, datetime] | None = None,
    ) -> list[dict[str, Any]]:
        default_as_of = datetime.now(timezone.utc)

        async with self._session_factory() as session:
            result = await session.execute(
                select(Lead)
                .options(selectinload(Lead.events))
                .where(Lead.id.in_(lead_ids))
            )
            leads = result.scalars().all()

        results = []
        for lead in leads:
            as_of = (as_of_dates or {}).get(lead.id, default_as_of)
            results.append(self._compute_for_lead(lead, lead.events, as_of))

        return results
