import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config.settings import get_settings
from src.models import Base

settings = get_settings()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def async_test_engine():
    engine = create_async_engine(settings.database.url)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(loop_scope="session")
async def db_session(async_test_engine) -> AsyncGenerator[AsyncSession, None]:
    async with async_test_engine.connect() as conn:
        await conn.begin()
        nested = await conn.begin_nested()
        session_factory = async_sessionmaker(
            bind=conn, class_=AsyncSession, expire_on_commit=False,
        )
        async with session_factory() as session:
            yield session
            if not nested.is_active:
                nested = await conn.begin_nested()
        await conn.rollback()


def make_lead_kwargs(**overrides) -> dict:
    defaults = {
        "external_id": f"test-{uuid.uuid4().hex[:8]}",
        "source_system": "kaggle",
    }
    defaults.update(overrides)
    return defaults


def make_event_kwargs(**overrides) -> dict:
    defaults = {
        "event_type": "page_view",
        "event_name": "Blog Post",
        "properties": {"url": "/blog/test", "session_id": "s-test-001"},
        "occurred_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    return defaults
