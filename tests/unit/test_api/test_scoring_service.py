"""Tests for ScoringService — uses mocks for model and feature computer."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import numpy as np
import pytest

from src.services.scoring import ScoringService, ScoreResult


def _make_mock_model(feature_names: list[str], importances: list[float]):
    """Create a mock sklearn Pipeline with predict_proba and feature importances."""
    model = MagicMock()
    model.predict_proba.return_value = np.array([[0.2, 0.8]])
    classifier = MagicMock()
    classifier.feature_importances_ = np.array(importances)
    model.named_steps = {"classifier": classifier}
    preprocessor = MagicMock()
    preprocessor.get_feature_names_out.return_value = np.array(feature_names)
    model.__getitem__ = MagicMock(return_value=preprocessor)
    return model


def _make_feature_dict(lead_id, feature_names):
    """Create a feature dict as FeatureComputer would return."""
    d = {name: 0.0 for name in feature_names}
    d["lead_id"] = lead_id
    d["computed_at"] = datetime.now(timezone.utc)
    return d


class TestBucketAssignment:
    def test_bucket_a(self):
        assert ScoringService.assign_bucket(0.85, 0.7, 0.4, 0.2) == "A"

    def test_bucket_b(self):
        assert ScoringService.assign_bucket(0.5, 0.7, 0.4, 0.2) == "B"

    def test_bucket_c(self):
        assert ScoringService.assign_bucket(0.3, 0.7, 0.4, 0.2) == "C"

    def test_bucket_d(self):
        assert ScoringService.assign_bucket(0.1, 0.7, 0.4, 0.2) == "D"

    def test_boundary_a(self):
        assert ScoringService.assign_bucket(0.7, 0.7, 0.4, 0.2) == "A"

    def test_boundary_b(self):
        assert ScoringService.assign_bucket(0.4, 0.7, 0.4, 0.2) == "B"

    def test_boundary_c(self):
        assert ScoringService.assign_bucket(0.2, 0.7, 0.4, 0.2) == "C"


class TestTopFactors:
    def test_returns_top_5_sorted_by_abs_importance(self):
        names = ["f1", "f2", "f3", "f4", "f5", "f6"]
        importances = [0.05, 0.30, 0.10, 0.25, 0.20, 0.10]
        values = {"f1": 1, "f2": 2, "f3": 3, "f4": 4, "f5": 5, "f6": 6}

        factors = ScoringService.top_factors(names, importances, values, n=5)

        assert len(factors) == 5
        assert factors[0]["feature"] == "f2"
        assert factors[1]["feature"] == "f4"
        assert factors[0]["value"] == 2


class TestScoreLead:
    @pytest.fixture
    def feature_names(self):
        return ["total_visits", "total_time_spent", "page_views_per_visit"]

    @pytest.fixture
    def service(self, feature_names):
        model = _make_mock_model(feature_names, [0.5, 0.3, 0.2])
        feature_computer = AsyncMock()
        session = AsyncMock()
        svc = ScoringService(
            model=model,
            model_version="v1.0",
            feature_computer=feature_computer,
            session=session,
            bucket_a=0.7,
            bucket_b=0.4,
            bucket_c=0.2,
        )
        return svc

    async def test_score_lead_returns_score_result(self, service, feature_names):
        lead_id = uuid4()
        service._feature_computer.compute.return_value = _make_feature_dict(
            lead_id, feature_names,
        )

        result = await service.score_lead(lead_id)

        assert isinstance(result, ScoreResult)
        assert result.lead_id == lead_id
        assert result.score == pytest.approx(0.8)
        assert result.bucket == "A"
        assert result.model_version == "v1.0"
        assert len(result.top_factors) == 3

    async def test_score_lead_raises_not_found_for_missing_lead(self, service):
        from sqlalchemy.exc import NoResultFound
        from src.api.exceptions import LeadNotFoundError

        lead_id = uuid4()
        service._feature_computer.compute.side_effect = NoResultFound()

        with pytest.raises(LeadNotFoundError) as exc_info:
            await service.score_lead(lead_id)
        assert exc_info.value.lead_id == lead_id

    async def test_score_lead_logs_prediction(self, service, feature_names):
        lead_id = uuid4()
        service._feature_computer.compute.return_value = _make_feature_dict(
            lead_id, feature_names,
        )

        await service.score_lead(lead_id)

        service._session.add.assert_called_once()
        pred = service._session.add.call_args[0][0]
        assert pred.lead_id == lead_id
        assert pred.score == pytest.approx(0.8)
        service._session.commit.assert_awaited_once()


class TestScoreLeads:
    async def test_batch_returns_results_missing_and_errors(self):
        feature_names = ["f1", "f2"]
        model = _make_mock_model(feature_names, [0.6, 0.4])
        model.predict_proba.return_value = np.array([[0.3, 0.7]])

        id1, id2, id_missing = uuid4(), uuid4(), uuid4()

        feature_computer = AsyncMock()
        feature_computer.compute_batch.return_value = {
            id1: _make_feature_dict(id1, feature_names),
            id2: _make_feature_dict(id2, feature_names),
        }

        session = AsyncMock()

        svc = ScoringService(
            model=model,
            model_version="v1.0",
            feature_computer=feature_computer,
            session=session,
            bucket_a=0.7, bucket_b=0.4, bucket_c=0.2,
        )

        results, missing, errors = await svc.score_leads([id1, id2, id_missing])

        assert len(results) == 2
        assert missing == [id_missing]
        assert errors == []
        session.commit.assert_awaited_once()
