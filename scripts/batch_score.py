"""CLI entry point for batch scoring all (or recently modified) leads.

Usage:
    poetry run python scripts/batch_score.py                        # score all leads
    poetry run python scripts/batch_score.py --since 2026-03-01     # only modified since
    poetry run python scripts/batch_score.py --chunk-size 200       # smaller chunks
    poetry run python scripts/batch_score.py --skip-crm             # no CRM writeback
    poetry run python scripts/batch_score.py --dry-run              # compute only, no persistence

Intended to be called via cron for nightly batch scoring.
"""

import argparse
import asyncio
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sklearn.pipeline import Pipeline

from config.settings import get_settings
from src.models.database import async_engine
from src.models.lead import Lead
from src.services.crm.factory import get_crm_client
from src.services.crm.sync import CRMSyncService
from src.services.features.computer import FeatureComputer
from src.services.scoring import ScoringService

logger = structlog.get_logger()


async def _query_lead_ids(
    engine: AsyncEngine, since: datetime | None = None,
) -> list[UUID]:
    """Query lead IDs, optionally filtered by updated_at."""
    session_factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False,
    )
    async with session_factory() as session:
        stmt = select(Lead.id)
        if since is not None:
            stmt = stmt.where(Lead.updated_at >= since)
        result = await session.execute(stmt)
        return [row[0] for row in result.all()]


def _build_scoring_service(
    engine: AsyncEngine,
    session: AsyncSession,
    model: Pipeline,
    model_version: str,
    skip_crm: bool,
    dry_run: bool,
) -> ScoringService:
    """Assemble a ScoringService with all dependencies."""
    feature_computer = FeatureComputer(engine)
    settings = get_settings()

    crm_sync_service = None
    if not skip_crm and not dry_run:
        crm_client = get_crm_client(settings)
        if crm_client is not None:
            crm_sync_service = CRMSyncService(crm_client, session)

    return ScoringService(
        model=model,
        model_version=model_version,
        feature_computer=feature_computer,
        session=session,
        bucket_a=settings.model.bucket_a_threshold,
        bucket_b=settings.model.bucket_b_threshold,
        bucket_c=settings.model.bucket_c_threshold,
        crm_sync_service=crm_sync_service,
    )


async def run_batch(
    engine: AsyncEngine,
    model: Pipeline,
    model_version: str,
    chunk_size: int = 500,
    since: datetime | None = None,
    skip_crm: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Score leads in chunks. Returns a summary dict."""
    lead_ids = await _query_lead_ids(engine, since=since)

    total_scored = 0
    total_errors = 0
    total_missing = 0
    buckets: dict[str, int] = {"A": 0, "B": 0, "C": 0, "D": 0}
    start = time.monotonic()

    session_factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False,
    )

    for i in range(0, len(lead_ids), chunk_size):
        chunk_ids = lead_ids[i : i + chunk_size]

        async with session_factory() as session:
            svc = _build_scoring_service(
                engine, session, model, model_version, skip_crm, dry_run,
            )

            if dry_run:
                # score_leads commits internally; use a savepoint we can rollback
                async with session.begin_nested():
                    results, missing, errors = await svc.score_leads(chunk_ids)
                    # rollback the savepoint so nothing persists
                await session.rollback()
            else:
                results, missing, errors = await svc.score_leads(chunk_ids)

            total_scored += len(results)
            total_errors += len(errors)
            total_missing += len(missing)

            for r in results:
                buckets[r.bucket] = buckets.get(r.bucket, 0) + 1

        logger.info(
            "batch_chunk_complete",
            chunk=i // chunk_size + 1,
            scored=len(results),
            errors=len(errors),
            missing=len(missing),
        )

    elapsed = time.monotonic() - start

    return {
        "total_scored": total_scored,
        "total_errors": total_errors,
        "total_missing": total_missing,
        "buckets": buckets,
        "elapsed_seconds": round(elapsed, 2),
        "dry_run": dry_run,
        "crm_writeback": not skip_crm and not dry_run,
    }


async def main(
    chunk_size: int = 500,
    since: str | None = None,
    skip_crm: bool = False,
    dry_run: bool = False,
) -> None:
    from src.ml.serialization import load_model
    from src.models.model_registry import ModelRegistry

    settings = get_settings()

    # Load active model
    session_factory = async_sessionmaker(
        bind=async_engine, class_=AsyncSession, expire_on_commit=False,
    )
    async with session_factory() as session:
        result = await session.execute(
            select(ModelRegistry)
            .where(ModelRegistry.is_active.is_(True))
            .limit(1)
        )
        registry_row = result.scalar_one_or_none()

    if registry_row is None:
        print("No active model found in registry. Run train.py --set-active first.")
        return

    model = load_model(Path(registry_row.artifact_path))
    model_version = registry_row.version

    since_dt = None
    if since:
        since_dt = datetime.fromisoformat(since).replace(tzinfo=timezone.utc)

    print(f"Batch scoring: model={model_version}, chunk_size={chunk_size}, "
          f"since={since or 'all'}, skip_crm={skip_crm}, dry_run={dry_run}")

    summary = await run_batch(
        engine=async_engine,
        model=model,
        model_version=model_version,
        chunk_size=chunk_size,
        since=since_dt,
        skip_crm=skip_crm,
        dry_run=dry_run,
    )

    await async_engine.dispose()

    print(f"\n{'=' * 50}")
    print(f"Batch scoring complete")
    print(f"{'=' * 50}")
    print(f"  Total scored: {summary['total_scored']}")
    print(f"  Total errors: {summary['total_errors']}")
    print(f"  Total missing: {summary['total_missing']}")
    print(f"  Elapsed: {summary['elapsed_seconds']}s")
    print(f"  Dry run: {summary['dry_run']}")
    print(f"  CRM writeback: {summary['crm_writeback']}")
    print(f"\n  Bucket distribution:")
    for bucket in ("A", "B", "C", "D"):
        print(f"    {bucket}: {summary['buckets'].get(bucket, 0)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Batch score leads")
    parser.add_argument(
        "--chunk-size", type=int, default=500,
        help="Number of leads per batch (default: 500)",
    )
    parser.add_argument(
        "--since", type=str, default=None,
        help="Only score leads updated after this ISO datetime (e.g. 2026-03-01)",
    )
    parser.add_argument(
        "--skip-crm", action="store_true",
        help="Disable CRM writeback even if configured",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Compute scores but don't persist predictions or write back to CRM",
    )
    args = parser.parse_args()
    asyncio.run(main(
        chunk_size=args.chunk_size,
        since=args.since,
        skip_crm=args.skip_crm,
        dry_run=args.dry_run,
    ))
