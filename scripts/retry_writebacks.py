"""CLI entry point for retrying failed CRM writebacks.

Usage:
    poetry run python scripts/retry_writebacks.py [--max-retries 5] [--delay 300]

Intended to be called via cron.
"""
import argparse
import asyncio

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from config.settings import get_settings
from src.models.database import async_engine
from src.services.crm.factory import get_crm_client
from src.services.crm.retry import retry_pending_writebacks


async def main(max_retries: int, delay_seconds: int) -> None:
    settings = get_settings()
    crm_client = get_crm_client(settings)

    if crm_client is None:
        print("CRM_TYPE is 'none' — nothing to retry.")
        return

    session_factory = async_sessionmaker(
        bind=async_engine, class_=AsyncSession, expire_on_commit=False,
    )
    async with session_factory() as session:
        summary = await retry_pending_writebacks(
            session, crm_client, max_retries=max_retries, delay_seconds=delay_seconds,
        )

    if hasattr(crm_client, "close"):
        await crm_client.close()
    await async_engine.dispose()

    print(f"Retry sweep complete: {summary}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Retry failed CRM writebacks")
    parser.add_argument("--max-retries", type=int, default=5)
    parser.add_argument("--delay", type=int, default=300, help="Min seconds since last attempt")
    args = parser.parse_args()
    asyncio.run(main(args.max_retries, args.delay))
