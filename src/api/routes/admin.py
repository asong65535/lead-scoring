"""Admin endpoints for model management."""

from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import ModelInfoResponse, ReloadModelResponse
from src.ml.serialization import load_model
from src.models.database import get_session
from src.models.model_registry import ModelRegistry

logger = structlog.get_logger()

router = APIRouter()


@router.get("/model", response_model=ModelInfoResponse)
async def get_active_model(
    session: AsyncSession = Depends(get_session),
) -> ModelInfoResponse:
    result = await session.execute(
        select(ModelRegistry).where(ModelRegistry.is_active == True)  # noqa: E712
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="No active model found")

    return ModelInfoResponse(
        version=row.version,
        metrics=row.metrics or {},
        feature_columns=row.feature_columns or [],
        trained_at=row.trained_at,
        is_active=row.is_active,
    )


@router.post("/reload-model", response_model=ReloadModelResponse)
async def reload_model(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> ReloadModelResponse:
    result = await session.execute(
        select(ModelRegistry).where(ModelRegistry.is_active == True)  # noqa: E712
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=500, detail="No active model in registry")

    artifact_path = Path(row.artifact_path)
    if not artifact_path.exists():
        raise HTTPException(
            status_code=500,
            detail=f"Model artifact not found: {row.artifact_path}",
        )

    model = load_model(artifact_path)
    request.app.state.model = model
    request.app.state.model_version = row.version

    logger.info("model_reloaded", version=row.version, artifact_path=str(artifact_path))

    return ReloadModelResponse(
        version=row.version,
        message=f"Model {row.version} loaded successfully",
    )
