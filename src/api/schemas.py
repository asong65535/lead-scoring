"""Pydantic request/response models for the scoring API."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class TopFactor(BaseModel):
    """A single feature contribution to a score."""

    feature: str
    impact: float
    value: Any


class ScoreResponse(BaseModel):
    """Response for a single lead scoring request."""

    lead_id: UUID
    score: float = Field(ge=0.0, le=1.0)
    bucket: str = Field(pattern=r"^[ABCD]$")
    model_version: str
    top_factors: list[TopFactor]
    scored_at: datetime


class ScoreError(BaseModel):
    """Error entry for a lead that could not be scored."""

    lead_id: UUID
    error: str


class BatchScoreRequest(BaseModel):
    """Request body for batch scoring."""

    lead_ids: list[UUID] = Field(min_length=1, max_length=500)


class BatchScoreResponse(BaseModel):
    """Response for batch scoring — includes both successes and errors."""

    results: list[ScoreResponse]
    errors: list[ScoreError]


class ModelInfoResponse(BaseModel):
    """Response for GET /admin/model."""

    version: str
    metrics: dict[str, Any]
    feature_columns: list[str]
    trained_at: datetime
    is_active: bool


class ReloadModelResponse(BaseModel):
    """Response for POST /admin/reload-model."""

    version: str
    message: str
