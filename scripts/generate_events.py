"""Generate synthetic behavioral events for existing Kaggle leads."""

import asyncio
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from random import Random

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine

# Add project root to path so imports work when run as script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.models.event import Event, VALID_EVENT_TYPES
from src.models.lead import Lead

BATCH_SIZE = 500

PAGE_NAMES = [
    "Blog Post", "About Us", "Pricing", "Features",
    "Competitor Comparison", "Case Studies", "Documentation", "Contact Us",
]

FORM_NAMES = ["Demo Request", "Content Download", "Newsletter Signup"]

EMAIL_SUBJECTS = [
    "Unlock Your Potential with Our Platform",
    "New Features Just Launched",
    "Your Weekly Industry Digest",
    "Exclusive Offer Inside",
    "See How Teams Like Yours Succeed",
    "Getting Started Guide",
]

# Event type proportions: (min%, max%) for converted and non-converted
EVENT_TYPE_PROPORTIONS = {
    "converted": {
        "page_view":          (50, 60),
        "email_open":         (15, 20),
        "email_click":        (10, 15),
        "form_submission":    (5, 10),
        "email_unsubscribe":  (0, 2),
    },
    "non_converted": {
        "page_view":          (60, 70),
        "email_open":         (15, 25),
        "email_click":        (3, 5),
        "form_submission":    (1, 3),
        "email_unsubscribe":  (3, 5),
    },
}


def _pick_proportions(rng: Random, converted: bool) -> dict[str, float]:
    """Pick random proportions for event types, normalized to sum to 1."""
    key = "converted" if converted else "non_converted"
    raw = {}
    for etype, (lo, hi) in EVENT_TYPE_PROPORTIONS[key].items():
        raw[etype] = rng.uniform(lo, hi)
    total = sum(raw.values())
    return {k: v / total for k, v in raw.items()}


def _generate_timestamps(
    rng: Random,
    count: int,
    start: datetime,
    end: datetime,
    converted: bool,
) -> list[datetime]:
    """Generate event timestamps with burst patterns.

    Converted leads get increasing density toward the end.
    Non-converted leads get flat/declining density.
    """
    if count == 0:
        return []

    total_seconds = (end - start).total_seconds()
    if total_seconds <= 0:
        return [start] * count

    timestamps: list[datetime] = []
    current = start

    while len(timestamps) < count:
        remaining = count - len(timestamps)
        # Burst size: 2-5 events
        burst_size = min(rng.randint(2, 5), remaining)

        # For converted leads, bias burst start toward the end of the window
        if converted:
            progress = len(timestamps) / count
            # Quadratic bias toward the end
            position = rng.uniform(progress * 0.5, 1.0) ** 0.7
        else:
            # Flat/declining: bias toward start
            position = rng.uniform(0, 0.8) ** 1.3

        burst_start_offset = position * total_seconds
        burst_start = start + timedelta(seconds=burst_start_offset)

        for i in range(burst_size):
            # Events within a burst are minutes apart
            offset_minutes = rng.uniform(0, 180)  # within a few hours
            ts = burst_start + timedelta(minutes=offset_minutes * i / max(burst_size, 1))
            if ts > end:
                ts = end - timedelta(seconds=rng.randint(0, 3600))
            timestamps.append(ts)

    timestamps = timestamps[:count]
    timestamps.sort()
    return timestamps


def _generate_event_properties(
    rng: Random,
    event_type: str,
    event_timestamps: list[tuple[str, datetime]],
    idx: int,
) -> tuple[str | None, dict]:
    """Generate event_name and properties for an event."""
    if event_type == "page_view":
        page = rng.choice(PAGE_NAMES)
        event_name = page
        session_id = None

        # Check if this page_view is within 30 min of a preceding page_view
        if idx > 0:
            prev_type, prev_ts = event_timestamps[idx - 1]
            curr_ts = event_timestamps[idx][1]
            if prev_type == "page_view" and (curr_ts - prev_ts).total_seconds() <= 1800:
                # Inherit session from previous (will be resolved in a second pass)
                session_id = "inherit"

        if session_id is None:
            session_id = f"s-{rng.randbytes(6).hex()}"

        props = {
            "url": f"/{page.lower().replace(' ', '-')}",
            "duration_seconds": rng.randint(10, 300),
            "session_id": session_id,
        }
        return event_name, props

    elif event_type == "email_open":
        email_id = f"e-{rng.randbytes(6).hex()}"
        subject = rng.choice(EMAIL_SUBJECTS)
        return None, {"email_id": email_id, "subject": subject}

    elif event_type == "email_click":
        email_id = f"e-{rng.randbytes(6).hex()}"
        page = rng.choice(PAGE_NAMES)
        return None, {"email_id": email_id, "link_url": f"/{page.lower().replace(' ', '-')}"}

    elif event_type == "form_submission":
        form_name = rng.choice(FORM_NAMES)
        form_id = f"f-{rng.randbytes(6).hex()}"
        return form_name, {"form_id": form_id}

    elif event_type == "email_unsubscribe":
        email_id = f"e-{rng.randbytes(6).hex()}"
        return None, {"email_id": email_id}

    return None, {}


def _build_events_for_lead(
    rng: Random,
    lead_id: uuid.UUID,
    converted: bool,
    window_days: int,
) -> tuple[list[dict], datetime | None]:
    """Build event records for a single lead.

    Returns (events_list, converted_at_or_none).
    """
    if converted:
        num_events = rng.randint(15, 50)
    else:
        num_events = rng.randint(3, 20)

    now = datetime.now(timezone.utc)
    start = now - timedelta(days=window_days)
    end = now - timedelta(days=1)

    timestamps = _generate_timestamps(rng, num_events, start, end, converted)

    # Pick proportions and assign event types
    proportions = _pick_proportions(rng, converted)
    event_types: list[str] = []
    for etype, frac in proportions.items():
        count = max(round(frac * num_events), 0)
        event_types.extend([etype] * count)

    # Adjust to match num_events
    while len(event_types) < num_events:
        event_types.append("page_view")
    while len(event_types) > num_events:
        event_types.pop()

    rng.shuffle(event_types)

    # Build (type, timestamp) pairs sorted by time
    event_pairs: list[tuple[str, datetime]] = list(zip(event_types, timestamps))
    event_pairs.sort(key=lambda x: x[1])

    # Generate properties and resolve sessions
    events: list[dict] = []
    current_session_id: str | None = None

    for i, (etype, ts) in enumerate(event_pairs):
        event_name, props = _generate_event_properties(rng, etype, event_pairs, i)

        # Resolve session inheritance for page_views
        if etype == "page_view":
            if props.get("session_id") == "inherit" and current_session_id is not None:
                props["session_id"] = current_session_id
            else:
                current_session_id = props["session_id"]
        else:
            # Non page_view breaks session chain
            current_session_id = None

        events.append({
            "id": uuid.uuid4(),
            "lead_id": lead_id,
            "event_type": etype,
            "event_name": event_name,
            "properties": props,
            "occurred_at": ts,
        })

    # Conversion date for converted leads
    converted_at = None
    if converted and events:
        first_event_ts = events[0]["occurred_at"]
        days_to_convert = rng.randint(7, 90)
        converted_at = first_event_ts + timedelta(days=days_to_convert)

    return events, converted_at


async def generate_events(
    engine: AsyncEngine | None = None,
    window_days: int = 180,
    seed: int = 42,
) -> dict:
    """Generate synthetic events for all leads without existing events.

    Returns summary dict with keys:
        leads_processed, leads_skipped, total_events, events_by_type
    """
    if engine is None:
        from src.models.database import async_engine
        engine = async_engine

    rng = Random(seed)

    # Fetch leads that have zero events
    async with engine.begin() as conn:
        has_events_subq = select(Event.lead_id).distinct().subquery()
        stmt = (
            select(Lead.__table__.c.id, Lead.__table__.c.converted)
            .outerjoin(has_events_subq, Lead.__table__.c.id == has_events_subq.c.lead_id)
            .where(has_events_subq.c.lead_id.is_(None))
        )
        result = await conn.execute(stmt)
        leads = result.fetchall()

    # Also count leads that already have events (skipped)
    async with engine.begin() as conn:
        total_leads_result = await conn.execute(select(Lead.__table__.c.id))
        total_leads = len(total_leads_result.fetchall())

    leads_skipped = total_leads - len(leads)
    leads_processed = 0
    total_events = 0
    events_by_type: dict[str, int] = {t: 0 for t in VALID_EVENT_TYPES}
    all_event_records: list[dict] = []
    converted_at_updates: list[tuple[uuid.UUID, datetime]] = []

    for lead_id, converted in leads:
        is_converted = converted is True
        events, converted_at = _build_events_for_lead(rng, lead_id, is_converted, window_days)

        all_event_records.extend(events)
        for e in events:
            events_by_type[e["event_type"]] += 1

        if converted_at is not None:
            converted_at_updates.append((lead_id, converted_at))

        leads_processed += 1
        total_events += len(events)

    # Batch insert events
    async with engine.begin() as conn:
        for i in range(0, len(all_event_records), BATCH_SIZE):
            batch = all_event_records[i : i + BATCH_SIZE]
            stmt = insert(Event.__table__).values(batch)
            await conn.execute(stmt)

        # Update converted_at on converted leads
        for lead_id, converted_at in converted_at_updates:
            stmt = (
                update(Lead.__table__)
                .where(Lead.__table__.c.id == lead_id)
                .values(converted_at=converted_at)
            )
            await conn.execute(stmt)

    summary = {
        "leads_processed": leads_processed,
        "leads_skipped": leads_skipped,
        "total_events": total_events,
        "events_by_type": dict(events_by_type),
    }
    return summary


def print_summary(summary: dict) -> None:
    """Print generation summary to stdout."""
    print("\n=== Event Generation Summary ===")
    print(f"Leads processed:     {summary['leads_processed']}")
    print(f"Leads skipped:       {summary['leads_skipped']}")
    print(f"Total events:        {summary['total_events']}")
    print("\nEvents by type:")
    for etype, count in summary["events_by_type"].items():
        pct = count / summary["total_events"] * 100 if summary["total_events"] > 0 else 0
        print(f"  {etype:25s} {count:6d}  ({pct:5.1f}%)")
    print()


if __name__ == "__main__":
    summary = asyncio.run(generate_events())
    print_summary(summary)
