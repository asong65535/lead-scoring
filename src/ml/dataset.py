"""Training data extraction.

Queries leads with known outcomes, computes point-in-time features via
FeatureComputer.compute_batch(), and returns train/test DataFrames.
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.models.event import Event
from src.models.lead import Lead
from src.ml.preprocessing import FIRMOGRAPHIC_PLACEHOLDERS, MVP_FEATURE_NAMES
from src.services.features.computer import FeatureComputer


def compute_as_of_date(
    converted: bool,
    converted_at: datetime | None,
    created_at: datetime,
    latest_event_at: datetime | None,
    now: datetime,
) -> datetime:
    """Determine the point-in-time cutoff for feature computation.

    - Converted leads: converted_at - 1 day
    - Non-converted leads: min(created_at + 90d, now, latest_event_at)
    """
    if converted and converted_at is not None:
        return converted_at - timedelta(days=1)

    candidates = [created_at + timedelta(days=90), now]
    if latest_event_at is not None:
        candidates.append(latest_event_at)
    return min(candidates)


def prepare_dataframe(
    feature_dicts: list[dict],
    labels: list[bool],
    as_of_dates: list[datetime],
) -> pd.DataFrame:
    """Convert feature dicts to a clean DataFrame with label and as_of_date columns.

    Drops: lead_id, computed_at, firmographic placeholders.
    Adds: converted (label), as_of_date (for time-based split).
    """
    df = pd.DataFrame(feature_dicts)
    drop_cols = ["lead_id", "computed_at"] + [n for n in FIRMOGRAPHIC_PLACEHOLDERS if n in df.columns]
    df = df.drop(columns=drop_cols)
    df["converted"] = labels
    df["as_of_date"] = as_of_dates
    return df


async def build_training_dataset(
    engine: AsyncEngine,
    test_fraction: float = 0.2,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build labeled training and test DataFrames from the database.

    Returns (train_df, test_df) with 17 MVP feature columns + 'converted' label.
    """
    now = datetime.now(timezone.utc)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    # Query leads with known outcomes and their latest event date in one query
    async with session_factory() as session:
        latest_event_subq = (
            select(
                Event.lead_id,
                func.max(Event.occurred_at).label("latest_event_at"),
            )
            .group_by(Event.lead_id)
            .subquery()
        )

        result = await session.execute(
            select(
                Lead.id,
                Lead.converted,
                Lead.converted_at,
                Lead.created_at,
                latest_event_subq.c.latest_event_at,
            )
            .outerjoin(latest_event_subq, Lead.id == latest_event_subq.c.lead_id)
            .where(Lead.converted.is_not(None))
        )
        lead_rows = result.all()

    # Filter: converted=True must have converted_at
    valid_leads = []
    for row in lead_rows:
        if row.converted and row.converted_at is None:
            continue
        valid_leads.append(row)

    if not valid_leads:
        raise ValueError("No labeled leads found in database")

    lead_ids = [r.id for r in valid_leads]

    # Compute as_of_dates
    as_of_dates = {}
    for row in valid_leads:
        as_of_dates[row.id] = compute_as_of_date(
            converted=row.converted,
            converted_at=row.converted_at,
            created_at=row.created_at,
            latest_event_at=row.latest_event_at,
            now=now,
        )

    # Compute features via FeatureComputer
    computer = FeatureComputer(engine=engine)
    features_by_id = await computer.compute_batch(lead_ids, as_of_dates=as_of_dates)

    # Build lookup for labels
    label_by_id = {r.id: r.converted for r in valid_leads}

    # Align features, labels, and as_of_dates by lead_id
    feature_dicts = []
    labels = []
    aod_list = []
    for lid, feat in features_by_id.items():
        feature_dicts.append(feat)
        labels.append(label_by_id[lid])
        aod_list.append(as_of_dates[lid])

    df = prepare_dataframe(feature_dicts, labels, aod_list)

    # Time-based split
    df = df.sort_values("as_of_date").reset_index(drop=True)
    split_idx = int(len(df) * (1 - test_fraction))

    train_df = df.iloc[:split_idx].drop(columns=["as_of_date"]).reset_index(drop=True)
    test_df = df.iloc[split_idx:].drop(columns=["as_of_date"]).reset_index(drop=True)

    return train_df, test_df
