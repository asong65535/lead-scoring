"""Save, load, and register trained model artifacts.

- save_model / load_model: filesystem operations via joblib (sync)
- register_model: writes to model_registry DB table (async)
- next_version: auto-increment version string from existing versions
"""

from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import joblib
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sklearn.pipeline import Pipeline

from src.models.model_registry import ModelRegistry


def save_model(
    model: Pipeline,
    version: str,
    metrics: dict,
    hyperparameters: dict,
    feature_columns: list[str],
    base_dir: Path = Path("models"),
) -> Path:
    """Save model pipeline to disk via joblib."""
    base_dir.mkdir(parents=True, exist_ok=True)
    path = base_dir / f"{version}.joblib"
    joblib.dump(model, path)
    return path


def load_model(artifact_path: Path) -> Pipeline:
    """Load model pipeline from disk."""
    return joblib.load(artifact_path)


def next_version(existing_versions: list[str]) -> str:
    """Compute next version string from existing versions.

    Finds the highest existing version and increments its minor.
    Major bumps are manual (e.g., when feature set changes in Phase 7+).
    """
    if not existing_versions:
        return "v1.0"

    max_major = 1
    max_minor = -1
    for v in existing_versions:
        parts = v.lstrip("v").split(".")
        if len(parts) == 2:
            major, minor = int(parts[0]), int(parts[1])
            if (major, minor) > (max_major, max_minor):
                max_major, max_minor = major, minor

    return f"v{max_major}.{max_minor + 1}"


async def get_existing_versions(engine: AsyncEngine) -> list[str]:
    """Query all version strings from model_registry."""
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        result = await session.execute(select(ModelRegistry.version))
        return [row[0] for row in result.all()]


async def register_model(
    engine: AsyncEngine,
    version: str,
    artifact_path: str,
    metrics: dict,
    hyperparameters: dict,
    feature_columns: list[str],
    set_active: bool = False,
) -> UUID:
    """Insert model into model_registry. Optionally set as active (deactivates others first)."""
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        async with session.begin():
            if set_active:
                await session.execute(
                    update(ModelRegistry).values(is_active=False)
                )

            result = await session.execute(
                insert(ModelRegistry.__table__)
                .values(
                    version=version,
                    artifact_path=artifact_path,
                    metrics=metrics,
                    hyperparameters=hyperparameters,
                    feature_columns=feature_columns,
                    is_active=set_active,
                    trained_at=datetime.now(timezone.utc),
                )
                .returning(ModelRegistry.__table__.c.id)
            )
            model_id = result.scalar_one()

    return model_id
