"""Shared fixtures for API integration tests.

Seeds leads, generates events, trains a tiny model, registers it,
and provides a TestClient with the real app.

Design note on event loops
--------------------------
pytest-asyncio runs the async fixtures on a session-scoped event loop.
FastAPI's TestClient (backed by anyio) runs requests on its *own* event loop.
Passing the session-scoped SQLAlchemy engine into the TestClient would cause
"Future attached to a different loop" errors.

The solution used here:
- All DB seeding / training is done through the session-scoped
  ``async_test_engine`` (normal pytest-asyncio fixtures).
- ``api_client`` creates a **fresh** engine (same URL, no pool) that lives
  only inside the TestClient's event loop, and overrides every engine
  reference the app uses.
"""

from uuid import UUID

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config.settings import get_settings
from src.api.main import create_app
from src.ml.dataset import build_training_dataset
from src.ml.preprocessing import MVP_FEATURE_NAMES, build_preprocessing_pipeline
from src.ml.serialization import load_model, register_model, save_model
from src.ml.trainer import train_model
from src.models import Event, Lead, ModelRegistry
from src.models.database import get_session
from src.models.prediction import Prediction
from scripts.generate_events import generate_events
from tests.conftest import make_lead_kwargs

_created_lead_ids: list[UUID] = []
_created_model_versions: list[str] = []


@pytest_asyncio.fixture(autouse=True)
async def cleanup(async_test_engine):
    yield
    async with async_test_engine.begin() as conn:
        for lid in _created_lead_ids:
            await conn.execute(delete(Event.__table__).where(Event.__table__.c.lead_id == lid))
            await conn.execute(delete(Prediction.__table__).where(Prediction.__table__.c.lead_id == lid))
            await conn.execute(delete(Lead.__table__).where(Lead.__table__.c.id == lid))
        for ver in _created_model_versions:
            await conn.execute(
                delete(ModelRegistry.__table__).where(ModelRegistry.__table__.c.version == ver)
            )
    _created_lead_ids.clear()
    _created_model_versions.clear()


async def _seed_leads(engine, n_converted=15, n_not_converted=25):
    lead_ids = []
    async with engine.begin() as conn:
        for _ in range(n_converted):
            kwargs = make_lead_kwargs(converted=True)
            result = await conn.execute(
                insert(Lead.__table__).values(**kwargs).returning(Lead.__table__.c.id)
            )
            lid = result.scalar_one()
            lead_ids.append(lid)
            _created_lead_ids.append(lid)
        for _ in range(n_not_converted):
            kwargs = make_lead_kwargs(converted=False)
            result = await conn.execute(
                insert(Lead.__table__).values(**kwargs).returning(Lead.__table__.c.id)
            )
            lid = result.scalar_one()
            lead_ids.append(lid)
            _created_lead_ids.append(lid)
    return lead_ids


@pytest_asyncio.fixture
async def seeded_leads(async_test_engine):
    lead_ids = await _seed_leads(async_test_engine)
    await generate_events(engine=async_test_engine, seed=42)
    return lead_ids


@pytest_asyncio.fixture
async def trained_model_path(async_test_engine, seeded_leads, tmp_path):
    """Train a tiny model, register it as active, and return the artifact path."""
    # Guard against a stale v99.0 left by a prior test (e.g. if cleanup was
    # skipped due to an earlier error in the same session).
    version = "v99.0"
    async with async_test_engine.begin() as conn:
        await conn.execute(
            delete(ModelRegistry.__table__).where(ModelRegistry.__table__.c.version == version)
        )

    train_df, test_df = await build_training_dataset(async_test_engine, test_fraction=0.2)

    pipeline = build_preprocessing_pipeline()
    result = train_model(
        train_df[MVP_FEATURE_NAMES], train_df["converted"],
        test_df[MVP_FEATURE_NAMES], test_df["converted"],
        pipeline,
    )

    _created_model_versions.append(version)
    artifact_path = save_model(
        result.model, version,
        result.metrics, result.hyperparameters,
        result.feature_columns, base_dir=tmp_path,
    )
    await register_model(
        async_test_engine, version, str(artifact_path),
        result.metrics, result.hyperparameters,
        result.feature_columns, set_active=True,
    )
    return artifact_path


@pytest.fixture
def api_client(trained_model_path, seeded_leads):
    """TestClient backed by a fresh engine that lives on its own event loop.

    ``trained_model_path`` and ``seeded_leads`` are consumed here so data
    is in the DB before the client makes any requests.  Tests that need
    ``seeded_leads`` request it as a separate fixture argument — pytest
    deduplicates fixture calls so the data is not inserted twice.
    """
    settings = get_settings()
    db_url = settings.database.url

    import src.api.routes.health as health_mod
    import src.api.dependencies as deps_mod
    import src.models.database as db_mod

    original_engine = db_mod.async_engine

    # Create a fresh engine bound to no specific event loop.
    # TestClient / anyio will adopt it on first use inside its own loop.
    fresh_engine = create_async_engine(db_url, pool_size=2, max_overflow=0)

    db_mod.async_engine = fresh_engine
    health_mod.async_engine = fresh_engine
    deps_mod.async_engine = fresh_engine

    # Disable auth for integration tests — auth middleware has its own unit tests.
    # Clear the lru_cache so create_app() picks up the patched value.
    get_settings.cache_clear()
    import os
    orig_auth = os.environ.get("AUTH_ENABLED")
    os.environ["AUTH_ENABLED"] = "false"
    try:
        app = create_app()
    finally:
        get_settings.cache_clear()
        if orig_auth is None:
            os.environ.pop("AUTH_ENABLED", None)
        else:
            os.environ["AUTH_ENABLED"] = orig_auth

    # Inject already-loaded model so lifespan doesn't try to re-query the DB
    model = load_model(trained_model_path)
    app.state.model = model
    app.state.model_version = "v99.0"

    # Override the per-request session factory to use the fresh engine
    fresh_session_factory = async_sessionmaker(
        bind=fresh_engine, class_=AsyncSession, expire_on_commit=False,
    )

    async def override_get_session():
        async with fresh_session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client

    # Restore original module-level engine
    db_mod.async_engine = original_engine
    health_mod.async_engine = original_engine
    deps_mod.async_engine = original_engine
