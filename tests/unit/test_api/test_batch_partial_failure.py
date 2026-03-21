"""Tests for batch scoring partial failure handling."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock
from uuid import uuid4

import numpy as np
import pytest

from src.services.scoring import ScoringService


@pytest.fixture
def mock_model():
    model = MagicMock()
    model.predict_proba.return_value = np.array([[0.2, 0.8]])
    preprocessor = MagicMock()
    preprocessor.get_feature_names_out.return_value = ["feat_a", "feat_b"]
    model.__getitem__ = MagicMock(return_value=preprocessor)
    model.named_steps = {"classifier": MagicMock(feature_importances_=np.array([0.6, 0.4]))}
    return model


@pytest.fixture
def mock_session():
    return AsyncMock()


async def test_batch_returns_errors_for_failed_leads(mock_model, mock_session):
    """If predict_proba fails for one lead, that lead appears in errors, others succeed."""
    lid_good = uuid4()
    lid_bad = uuid4()

    good_features = {"lead_id": lid_good, "computed_at": datetime.now(timezone.utc), "feat_a": 1.0, "feat_b": 0.5}
    bad_features = {"lead_id": lid_bad, "computed_at": datetime.now(timezone.utc), "feat_a": None, "feat_b": None}

    feature_computer = AsyncMock()
    feature_computer.compute_batch.return_value = {lid_good: good_features, lid_bad: bad_features}

    # Make predict_proba fail on the bad lead's data
    call_count = 0

    def side_effect(df):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise ValueError("Cannot predict on NaN")
        return np.array([[0.2, 0.8]])

    mock_model.predict_proba.side_effect = side_effect

    service = ScoringService(
        model=mock_model, model_version="v1", feature_computer=feature_computer,
        session=mock_session,
    )

    results, missing, errors = await service.score_leads([lid_good, lid_bad])

    assert len(results) == 1
    assert results[0].lead_id == lid_good
    assert len(errors) == 1
    assert errors[0][0] == lid_bad
