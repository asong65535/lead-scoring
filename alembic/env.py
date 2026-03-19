import asyncio
import sys
from pathlib import Path

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

# Add project root to path so imports work
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import get_settings
from src.models import Base  # noqa: E402 — triggers all model imports

settings = get_settings()
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database.sync_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    engine = create_async_engine(settings.database.url)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
