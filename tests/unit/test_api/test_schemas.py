"""Tests for API Pydantic schemas."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.api.schemas import (
    BatchScoreRequest,
    BatchScoreResponse,
    ScoreError,
    ScoreResponse,
    TopFactor,
    ModelInfoResponse,
)


class TestScoreResponse:
    def test_valid_score_response(self):
        resp = ScoreResponse(
            lead_id=uuid4(),
            score=0.85,
            bucket="A",
            model_version="v1.2",
            top_factors=[
                TopFactor(feature="total_visits", impact=0.15, value=42),
            ],
            scored_at=datetime.now(timezone.utc),
        )
        assert resp.bucket == "A"

    def test_bucket_must_be_valid(self):
        with pytest.raises(ValidationError):
            ScoreResponse(
                lead_id=uuid4(),
                score=0.5,
                bucket="X",
                model_version="v1.0",
                top_factors=[],
                scored_at=datetime.now(timezone.utc),
            )

    def test_score_must_be_between_0_and_1(self):
        with pytest.raises(ValidationError):
            ScoreResponse(
                lead_id=uuid4(),
                score=1.5,
                bucket="A",
                model_version="v1.0",
                top_factors=[],
                scored_at=datetime.now(timezone.utc),
            )


class TestBatchScoreRequest:
    def test_valid_batch_request(self):
        req = BatchScoreRequest(lead_ids=[uuid4() for _ in range(5)])
        assert len(req.lead_ids) == 5

    def test_empty_list_rejected(self):
        with pytest.raises(ValidationError):
            BatchScoreRequest(lead_ids=[])

    def test_over_500_rejected(self):
        with pytest.raises(ValidationError):
            BatchScoreRequest(lead_ids=[uuid4() for _ in range(501)])


class TestBatchScoreResponse:
    def test_contains_results_and_errors(self):
        resp = BatchScoreResponse(
            results=[],
            errors=[ScoreError(lead_id=uuid4(), error="Lead not found")],
        )
        assert len(resp.errors) == 1


class TestModelInfoResponse:
    def test_valid_model_info(self):
        resp = ModelInfoResponse(
            version="v1.2",
            metrics={"auc_roc": 0.92},
            feature_columns=["total_visits"],
            trained_at=datetime.now(timezone.utc),
            is_active=True,
        )
        assert resp.is_active is True
