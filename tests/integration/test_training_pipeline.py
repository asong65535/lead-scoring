"""Integration test for the full ML training pipeline."""

from datetime import datetime, timezone
from uuid import UUID

import numpy as np
import pytest
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from src.models import Event, Lead, ModelRegistry
from src.ml.dataset import build_training_dataset
from src.ml.preprocessing import build_preprocessing_pipeline, MVP_FEATURE_NAMES
from src.ml.trainer import train_model
from src.ml.serialization import save_model, load_model, register_model, next_version, get_existing_versions
from scripts.generate_events import generate_events
from tests.conftest import make_lead_kwargs

_created_lead_ids: list[UUID] = []
_created_model_versions: list[str] = []


@pytest.fixture(autouse=True)
async def cleanup(async_test_engine):
    yield
    async with async_test_engine.begin() as conn:
        for lid in _created_lead_ids:
            await conn.execute(delete(Event.__table__).where(Event.__table__.c.lead_id == lid))
            await conn.execute(delete(Lead.__table__).where(Lead.__table__.c.id == lid))
        for ver in _created_model_versions:
            await conn.execute(delete(ModelRegistry.__table__).where(ModelRegistry.__table__.c.version == ver))
    _created_lead_ids.clear()
    _created_model_versions.clear()


async def _seed_leads(engine, n_converted=20, n_not_converted=30):
    """Insert test leads with converted labels."""
    async with engine.begin() as conn:
        for _ in range(n_converted):
            kwargs = make_lead_kwargs(converted=True)
            result = await conn.execute(
                insert(Lead.__table__).values(**kwargs).returning(Lead.__table__.c.id)
            )
            _created_lead_ids.append(result.scalar_one())
        for _ in range(n_not_converted):
            kwargs = make_lead_kwargs(converted=False)
            result = await conn.execute(
                insert(Lead.__table__).values(**kwargs).returning(Lead.__table__.c.id)
            )
            _created_lead_ids.append(result.scalar_one())


async def test_end_to_end_training(async_test_engine, tmp_path):
    """Full pipeline: seed → generate events → build dataset → train → save → register."""
    await _seed_leads(async_test_engine, n_converted=20, n_not_converted=30)
    await generate_events(engine=async_test_engine, seed=42)

    train_df, test_df = await build_training_dataset(async_test_engine, test_fraction=0.2)

    assert len(train_df) > 0
    assert len(test_df) > 0
    assert "converted" in train_df.columns
    assert set(MVP_FEATURE_NAMES).issubset(set(train_df.columns))

    X_train = train_df[MVP_FEATURE_NAMES]
    y_train = train_df["converted"]
    X_test = test_df[MVP_FEATURE_NAMES]
    y_test = test_df["converted"]

    pipeline = build_preprocessing_pipeline()
    result = train_model(X_train, y_train, X_test, y_test, pipeline)

    assert 0.0 <= result.metrics["auc_roc"] <= 1.0
    assert len(result.feature_importance) == 17

    existing = await get_existing_versions(async_test_engine)
    version = next_version(existing)
    _created_model_versions.append(version)

    artifact_path = save_model(
        result.model, version,
        result.metrics, result.hyperparameters,
        result.feature_columns, base_dir=tmp_path,
    )
    assert artifact_path.exists()

    model_id = await register_model(
        async_test_engine, version, str(artifact_path),
        result.metrics, result.hyperparameters,
        result.feature_columns, set_active=True,
    )
    assert isinstance(model_id, UUID)

    # Verify model is in registry and active
    async with async_test_engine.connect() as conn:
        row = await conn.execute(
            select(ModelRegistry.__table__).where(ModelRegistry.__table__.c.version == version)
        )
        record = row.one()
    assert record.is_active is True
    assert record.metrics["auc_roc"] == result.metrics["auc_roc"]


async def test_saved_model_predicts_on_feature_dicts(async_test_engine, tmp_path):
    """Verify a saved model can score new feature dicts from FeatureComputer."""
    await _seed_leads(async_test_engine, n_converted=15, n_not_converted=25)
    await generate_events(engine=async_test_engine, seed=99)

    train_df, test_df = await build_training_dataset(async_test_engine, test_fraction=0.2)

    pipeline = build_preprocessing_pipeline()
    result = train_model(
        train_df[MVP_FEATURE_NAMES], train_df["converted"],
        test_df[MVP_FEATURE_NAMES], test_df["converted"],
        pipeline,
    )

    version = "v99.0"
    _created_model_versions.append(version)
    artifact_path = save_model(
        result.model, version,
        result.metrics, result.hyperparameters,
        result.feature_columns, base_dir=tmp_path,
    )

    loaded = load_model(artifact_path)
    # Create a single-row DataFrame from MVP feature defaults
    import pandas as pd
    sample = pd.DataFrame([{name: 0 for name in MVP_FEATURE_NAMES}])
    probas = loaded.predict_proba(sample)

    assert probas.shape == (1, 2)
    assert 0.0 <= probas[0, 1] <= 1.0


async def test_register_model_deactivates_previous(async_test_engine, tmp_path):
    """When set_active=True, previously active models should be deactivated."""
    await _seed_leads(async_test_engine, n_converted=15, n_not_converted=25)
    await generate_events(engine=async_test_engine, seed=77)

    train_df, test_df = await build_training_dataset(async_test_engine, test_fraction=0.2)
    pipeline = build_preprocessing_pipeline()
    result = train_model(
        train_df[MVP_FEATURE_NAMES], train_df["converted"],
        test_df[MVP_FEATURE_NAMES], test_df["converted"],
        pipeline,
    )

    # Register first model as active
    v1 = "v90.0"
    _created_model_versions.append(v1)
    path1 = save_model(
        result.model, v1,
        result.metrics, result.hyperparameters,
        result.feature_columns, base_dir=tmp_path,
    )
    id1 = await register_model(
        async_test_engine, v1, str(path1),
        result.metrics, result.hyperparameters,
        result.feature_columns, set_active=True,
    )

    # Register second model as active
    v2 = "v90.1"
    _created_model_versions.append(v2)
    path2 = save_model(
        result.model, v2,
        result.metrics, result.hyperparameters,
        result.feature_columns, base_dir=tmp_path,
    )
    id2 = await register_model(
        async_test_engine, v2, str(path2),
        result.metrics, result.hyperparameters,
        result.feature_columns, set_active=True,
    )

    # Verify: v1 should now be inactive, v2 active
    async with async_test_engine.connect() as conn:
        row1 = await conn.execute(
            select(ModelRegistry.__table__).where(ModelRegistry.__table__.c.version == v1)
        )
        record1 = row1.one()
        row2 = await conn.execute(
            select(ModelRegistry.__table__).where(ModelRegistry.__table__.c.version == v2)
        )
        record2 = row2.one()

    assert record1.is_active is False, "First model should be deactivated after second is registered as active"
    assert record2.is_active is True
