"""Scoring endpoints — single lead and batch."""

from uuid import UUID

from fastapi import APIRouter, Depends

from src.api.dependencies import get_scoring_service
from src.api.schemas import (
    BatchScoreRequest,
    BatchScoreResponse,
    ScoreError,
    ScoreResponse,
    TopFactor,
)
from src.services.scoring import ScoreResult, ScoringService

router = APIRouter()


def _to_response(result: ScoreResult) -> ScoreResponse:
    return ScoreResponse(
        lead_id=result.lead_id,
        score=result.score,
        bucket=result.bucket,
        model_version=result.model_version,
        top_factors=[TopFactor(**f) for f in result.top_factors],
        scored_at=result.scored_at,
    )


# /batch must be declared before /{lead_id} so FastAPI matches it literally
@router.post("/batch", response_model=BatchScoreResponse)
async def score_batch(
    body: BatchScoreRequest,
    service: ScoringService = Depends(get_scoring_service),
) -> BatchScoreResponse:
    results, missing_ids = await service.score_leads(body.lead_ids)
    return BatchScoreResponse(
        results=[_to_response(r) for r in results],
        errors=[ScoreError(lead_id=mid, error="Lead not found") for mid in missing_ids],
    )


@router.post("/{lead_id}", response_model=ScoreResponse)
async def score_lead(
    lead_id: UUID,
    service: ScoringService = Depends(get_scoring_service),
) -> ScoreResponse:
    result = await service.score_lead(lead_id)
    return _to_response(result)
