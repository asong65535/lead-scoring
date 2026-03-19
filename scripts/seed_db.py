"""Ingest Kaggle Lead Scoring CSV into Postgres."""

import asyncio
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine

# Add project root to path so imports work when run as script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.models.lead import Lead
from src.services.ingestion import clean_dataframe, validate_required_fields

CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "Lead Scoring.csv"
BATCH_SIZE = 500


async def ingest(csv_path: Path = CSV_PATH, engine: AsyncEngine | None = None) -> dict:
    """Read CSV, clean, insert into DB. Returns summary stats.

    Args:
        csv_path: Path to the CSV file.
        engine: SQLAlchemy async engine. If None, uses the default from database.py.
    """
    if engine is None:
        from src.models.database import async_engine
        engine = async_engine

    df = pd.read_csv(csv_path)
    total_read = len(df)

    cleaned = clean_dataframe(df)
    valid, rejected = validate_required_fields(cleaned)
    total_rejected = len(rejected)

    valid = valid.copy()
    valid["source_system"] = "kaggle"

    # Replace NaN/NA with None for DB insertion; to_dict can emit float('nan')
    # for StringDtype columns with missing values, which asyncpg rejects.
    import math

    def _clean(v):
        if v is None:
            return None
        if isinstance(v, float) and math.isnan(v):
            return None
        return v

    records = [
        {k: _clean(v) for k, v in row.items()}
        for row in valid.to_dict(orient="records")
    ]

    total_inserted = 0

    async with engine.begin() as conn:
        for i in range(0, len(records), BATCH_SIZE):
            batch = records[i : i + BATCH_SIZE]
            stmt = insert(Lead.__table__).values(batch)
            stmt = stmt.on_conflict_do_nothing(index_elements=["external_id"])
            result = await conn.execute(stmt)
            total_inserted += result.rowcount

    total_skipped = len(records) - total_inserted

    # Compute summary
    null_pcts = {}
    for col in valid.columns:
        if col == "source_system":
            continue
        null_count = valid[col].isna().sum()
        null_pcts[col] = round(null_count / len(valid) * 100, 1) if len(valid) > 0 else 0

    converted_count = valid["converted"].sum() if "converted" in valid.columns else 0
    conversion_rate = round(converted_count / len(valid) * 100, 1) if len(valid) > 0 else 0

    summary = {
        "total_read": total_read,
        "total_rejected": total_rejected,
        "total_skipped": total_skipped,
        "total_inserted": total_inserted,
        "null_percentages": null_pcts,
        "conversion_rate": conversion_rate,
    }
    return summary


def print_summary(summary: dict) -> None:
    """Print ingestion summary to stdout."""
    print("\n=== Ingestion Summary ===")
    print(f"Total rows read:     {summary['total_read']}")
    print(f"Rows rejected:       {summary['total_rejected']}")
    print(f"Rows skipped (dup):  {summary['total_skipped']}")
    print(f"Rows inserted:       {summary['total_inserted']}")
    print(f"Conversion rate:     {summary['conversion_rate']}%")
    print("\nNULL percentages per column:")
    for col, pct in summary["null_percentages"].items():
        print(f"  {col:30s} {pct:5.1f}%")
    print()


if __name__ == "__main__":
    summary = asyncio.run(ingest())
    print_summary(summary)
