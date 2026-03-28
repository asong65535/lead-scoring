"""Tests for batch scoring worker — scripts/batch_score.py."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, call, patch
from uuid import uuid4

import numpy as np
import pytest

from src.services.scoring import ScoreResult


def _make_score_result(lead_id, bucket="A"):
    return ScoreResult(
        lead_id=lead_id,
        score=0.75,
        bucket=bucket,
        model_version="v1.0",
        top_factors=[{"feature": "f1", "impact": 0.5, "value": 1.0}],
        scored_at=datetime.now(timezone.utc),
    )


def _make_mock_scoring_service(results_by_chunk):
    """Create a mock ScoringService whose score_leads returns pre-set results per call.

    results_by_chunk: list of (results, missing, errors) tuples, one per call.
    """
    svc = AsyncMock()
    svc.score_leads = AsyncMock(side_effect=results_by_chunk)
    return svc


class TestRunBatch:
    """Tests for the run_batch() core async function."""

    @patch("scripts.batch_score._query_lead_ids")
    @patch("scripts.batch_score._build_scoring_service")
    async def test_scores_all_leads_in_chunks(
        self, mock_build_svc, mock_query_ids,
    ):
        """Leads are chunked and each chunk is scored via ScoringService."""
        from scripts.batch_score import run_batch

        ids = [uuid4() for _ in range(5)]
        mock_query_ids.return_value = ids

        # chunk_size=2 -> 3 chunks: [2, 2, 1]
        chunk_results = [
            ([_make_score_result(ids[0]), _make_score_result(ids[1])], [], []),
            ([_make_score_result(ids[2]), _make_score_result(ids[3])], [], []),
            ([_make_score_result(ids[4])], [], []),
        ]
        mock_svc = _make_mock_scoring_service(chunk_results)
        mock_build_svc.return_value = mock_svc

        summary = await run_batch(
            engine=AsyncMock(),
            model=MagicMock(),
            model_version="v1.0",
            chunk_size=2,
            since=None,
            skip_crm=False,
            dry_run=False,
        )

        assert summary["total_scored"] == 5
        assert summary["total_errors"] == 0
        assert mock_svc.score_leads.call_count == 3

    @patch("scripts.batch_score._query_lead_ids")
    @patch("scripts.batch_score._build_scoring_service")
    async def test_since_flag_passed_to_query(
        self, mock_build_svc, mock_query_ids,
    ):
        """The since parameter is forwarded to _query_lead_ids."""
        from scripts.batch_score import run_batch

        mock_query_ids.return_value = []
        mock_build_svc.return_value = AsyncMock()
        cutoff = datetime(2026, 3, 1, tzinfo=timezone.utc)

        await run_batch(
            engine=AsyncMock(),
            model=MagicMock(),
            model_version="v1.0",
            chunk_size=500,
            since=cutoff,
            skip_crm=False,
            dry_run=False,
        )

        _, kwargs = mock_query_ids.call_args
        assert kwargs.get("since") == cutoff or mock_query_ids.call_args[0][-1] == cutoff

    @patch("scripts.batch_score._query_lead_ids")
    @patch("scripts.batch_score._build_scoring_service")
    async def test_dry_run_skips_persistence(
        self, mock_build_svc, mock_query_ids,
    ):
        """In dry-run mode, summary reflects dry_run=True."""
        from scripts.batch_score import run_batch

        ids = [uuid4()]
        mock_query_ids.return_value = ids
        mock_svc = _make_mock_scoring_service([
            ([_make_score_result(ids[0])], [], []),
        ])
        mock_build_svc.return_value = mock_svc

        summary = await run_batch(
            engine=AsyncMock(),
            model=MagicMock(),
            model_version="v1.0",
            chunk_size=500,
            since=None,
            skip_crm=False,
            dry_run=True,
        )

        assert summary["dry_run"] is True

    @patch("scripts.batch_score._query_lead_ids")
    @patch("scripts.batch_score._build_scoring_service")
    async def test_skip_crm_disables_writeback(
        self, mock_build_svc, mock_query_ids,
    ):
        """When skip_crm=True, summary reflects crm_writeback=False."""
        from scripts.batch_score import run_batch

        mock_query_ids.return_value = []
        mock_build_svc.return_value = AsyncMock()

        summary = await run_batch(
            engine=AsyncMock(),
            model=MagicMock(),
            model_version="v1.0",
            chunk_size=500,
            since=None,
            skip_crm=True,
            dry_run=False,
        )

        assert summary["crm_writeback"] is False

    @patch("scripts.batch_score._query_lead_ids")
    @patch("scripts.batch_score._build_scoring_service")
    async def test_reports_bucket_distribution(
        self, mock_build_svc, mock_query_ids,
    ):
        """Summary includes count per bucket."""
        from scripts.batch_score import run_batch

        ids = [uuid4() for _ in range(4)]
        mock_query_ids.return_value = ids
        mock_svc = _make_mock_scoring_service([
            (
                [
                    _make_score_result(ids[0], bucket="A"),
                    _make_score_result(ids[1], bucket="B"),
                    _make_score_result(ids[2], bucket="C"),
                    _make_score_result(ids[3], bucket="D"),
                ],
                [],
                [],
            ),
        ])
        mock_build_svc.return_value = mock_svc

        summary = await run_batch(
            engine=AsyncMock(),
            model=MagicMock(),
            model_version="v1.0",
            chunk_size=500,
            since=None,
            skip_crm=True,
            dry_run=False,
        )

        assert summary["buckets"] == {"A": 1, "B": 1, "C": 1, "D": 1}

    @patch("scripts.batch_score._query_lead_ids")
    @patch("scripts.batch_score._build_scoring_service")
    async def test_accumulates_errors_across_chunks(
        self, mock_build_svc, mock_query_ids,
    ):
        """Errors from individual chunks are accumulated in the summary."""
        from scripts.batch_score import run_batch

        ids = [uuid4() for _ in range(4)]
        mock_query_ids.return_value = ids
        mock_svc = _make_mock_scoring_service([
            ([_make_score_result(ids[0])], [], [(ids[1], "feature error")]),
            ([], [ids[2]], [(ids[3], "model error")]),
        ])
        mock_build_svc.return_value = mock_svc

        summary = await run_batch(
            engine=AsyncMock(),
            model=MagicMock(),
            model_version="v1.0",
            chunk_size=2,
            since=None,
            skip_crm=True,
            dry_run=False,
        )

        assert summary["total_scored"] == 1
        assert summary["total_errors"] == 2
        assert summary["total_missing"] == 1
