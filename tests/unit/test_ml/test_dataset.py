"""Unit tests for dataset builder helper functions."""

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from src.ml.dataset import compute_as_of_date, prepare_dataframe
from src.ml.preprocessing import MVP_FEATURE_NAMES, FIRMOGRAPHIC_PLACEHOLDERS


NOW = datetime(2026, 3, 20, tzinfo=timezone.utc)


class TestComputeAsOfDate:
    def test_converted_uses_converted_at_minus_one_day(self):
        converted_at = datetime(2026, 3, 10, tzinfo=timezone.utc)
        result = compute_as_of_date(
            converted=True,
            converted_at=converted_at,
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            latest_event_at=None,
            now=NOW,
        )
        assert result == converted_at - timedelta(days=1)

    def test_non_converted_uses_created_plus_90_capped_at_now(self):
        created_at = datetime(2026, 3, 1, tzinfo=timezone.utc)
        # created_at + 90 = June 1, but now = March 20, so capped at now
        result = compute_as_of_date(
            converted=False,
            converted_at=None,
            created_at=created_at,
            latest_event_at=None,
            now=NOW,
        )
        assert result == NOW

    def test_non_converted_picks_minimum_of_candidates(self):
        created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
        latest_event = datetime(2025, 6, 1, tzinfo=timezone.utc)
        # created_at + 90 = April 1 2025, latest_event = June 1 2025
        # min(April 1, now=March 2026, June 1) = April 1
        result = compute_as_of_date(
            converted=False,
            converted_at=None,
            created_at=created_at,
            latest_event_at=latest_event,
            now=NOW,
        )
        assert result == created_at + timedelta(days=90)

    def test_non_converted_created_plus_90_when_all_later(self):
        created_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
        latest_event = datetime(2025, 10, 1, tzinfo=timezone.utc)
        # created_at + 90 = Aug 29, latest_event = Oct 1, now = March 2026
        # min(Aug 29, March 2026, Oct 1) = Aug 29
        result = compute_as_of_date(
            converted=False,
            converted_at=None,
            created_at=created_at,
            latest_event_at=latest_event,
            now=NOW,
        )
        assert result == created_at + timedelta(days=90)

    def test_non_converted_no_events_uses_min_of_created_plus_90_and_now(self):
        created_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
        result = compute_as_of_date(
            converted=False,
            converted_at=None,
            created_at=created_at,
            latest_event_at=None,
            now=NOW,
        )
        # created_at + 90 = Aug 29 2025, now = March 2026 → Aug 29
        assert result == created_at + timedelta(days=90)


class TestTimeSplit:
    def test_time_based_split_oldest_to_train(self):
        """Verify train gets oldest rows, test gets newest rows by as_of_date."""
        feature_dicts = [
            {"lead_id": f"id{i}", "computed_at": NOW, **{n: i for n in MVP_FEATURE_NAMES}, **{n: "x" for n in FIRMOGRAPHIC_PLACEHOLDERS}}
            for i in range(10)
        ]
        # as_of_dates are deliberately out of order to test sorting
        dates = [NOW - timedelta(days=d) for d in [5, 9, 1, 8, 3, 7, 2, 6, 4, 0]]
        labels = [True] * 5 + [False] * 5

        df = prepare_dataframe(feature_dicts, labels, dates)
        df = df.sort_values("as_of_date").reset_index(drop=True)
        split_idx = int(len(df) * 0.8)
        train_df = df.iloc[:split_idx]
        test_df = df.iloc[split_idx:]

        assert len(train_df) == 8
        assert len(test_df) == 2
        # Train's max as_of_date should be <= test's min as_of_date
        assert train_df["as_of_date"].max() <= test_df["as_of_date"].min()


class TestPrepareDataframe:
    def test_drops_metadata_and_firmographic_columns(self):
        """prepare_dataframe should drop lead_id, computed_at, and firmographic cols."""
        feature_dicts = [
            {
                "lead_id": "abc",
                "computed_at": NOW,
                **{name: 0 for name in MVP_FEATURE_NAMES},
                **{name: "unknown" for name in FIRMOGRAPHIC_PLACEHOLDERS},
            },
        ]
        labels = [True]
        as_of_dates = [NOW]

        df = prepare_dataframe(feature_dicts, labels, as_of_dates)

        assert "lead_id" not in df.columns
        assert "computed_at" not in df.columns
        for name in FIRMOGRAPHIC_PLACEHOLDERS:
            assert name not in df.columns
        assert "converted" in df.columns
        assert "as_of_date" in df.columns
        # 17 features + converted + as_of_date
        assert len(df.columns) == 19

    def test_preserves_label_values(self):
        feature_dicts = [
            {"lead_id": "a", "computed_at": NOW, **{n: 0 for n in MVP_FEATURE_NAMES}, **{n: "x" for n in FIRMOGRAPHIC_PLACEHOLDERS}},
            {"lead_id": "b", "computed_at": NOW, **{n: 0 for n in MVP_FEATURE_NAMES}, **{n: "x" for n in FIRMOGRAPHIC_PLACEHOLDERS}},
        ]
        labels = [True, False]
        as_of_dates = [NOW, NOW - timedelta(days=1)]

        df = prepare_dataframe(feature_dicts, labels, as_of_dates)

        assert list(df["converted"]) == [True, False]
