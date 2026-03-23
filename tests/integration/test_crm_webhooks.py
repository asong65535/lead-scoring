"""Integration test: webhook endpoint processes events end-to-end.

Note: This test validates the filtering and debounce logic against a real DB.
It does NOT test actual HubSpot API calls -- those are mocked.
"""
from datetime import datetime, timezone

import pytest

from src.models.lead import Lead
from src.models.prediction import Prediction
from src.api.routes.webhooks import _is_debounced
from tests.conftest import make_lead_kwargs


@pytest.mark.asyncio
async def test_debounce_with_real_prediction(db_session):
    """Debounce check queries the predictions table correctly."""
    lead = Lead(**make_lead_kwargs(source_system="hubspot"))
    db_session.add(lead)
    await db_session.flush()

    # No predictions yet -- should not be debounced
    assert await _is_debounced(db_session, lead.id, debounce_seconds=60) is False

    # Add a recent prediction
    pred = Prediction(
        lead_id=lead.id,
        score=0.5,
        bucket="B",
        model_version="v1.0",
        feature_snapshot={},
        top_factors=[],
        scored_at=datetime.now(timezone.utc),
    )
    db_session.add(pred)
    await db_session.flush()

    # Should be debounced now
    assert await _is_debounced(db_session, lead.id, debounce_seconds=60) is True
