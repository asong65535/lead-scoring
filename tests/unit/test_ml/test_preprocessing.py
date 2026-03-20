"""Unit tests for preprocessing pipeline."""

import numpy as np
import pandas as pd
import pytest

from src.ml.preprocessing import build_preprocessing_pipeline, FIRMOGRAPHIC_PLACEHOLDERS, MVP_FEATURE_NAMES

# The 17 MVP feature names (excluding 3 firmographic placeholders)
NUMERIC_FEATURES = [
    "days_since_last_visit", "days_since_last_email_open", "days_since_first_touch",
    "total_pageviews_7d", "total_pageviews_30d", "total_sessions",
    "emails_opened_30d", "emails_clicked_30d", "avg_pages_per_session",
    "avg_session_duration_seconds", "pricing_page_views", "engagement_velocity_7d",
]
BOOLEAN_FEATURES = [
    "viewed_pricing", "requested_demo", "downloaded_content",
    "visited_competitor_comparison", "is_engagement_increasing",
]


@pytest.fixture
def sample_df():
    """DataFrame mimicking FeatureComputer output (minus firmographic + metadata cols)."""
    return pd.DataFrame([
        {**{n: 0.0 for n in NUMERIC_FEATURES}, **{b: False for b in BOOLEAN_FEATURES}},
        {**{n: 1.0 for n in NUMERIC_FEATURES}, **{b: True for b in BOOLEAN_FEATURES}},
    ])


def test_pipeline_output_shape(sample_df):
    pipeline = build_preprocessing_pipeline()
    result = pipeline.fit_transform(sample_df)
    assert result.shape == (2, 17)


def test_numeric_features_pass_through(sample_df):
    pipeline = build_preprocessing_pipeline()
    result = pipeline.fit_transform(sample_df)
    assert all(result[0, :12] == 0.0)
    assert all(result[1, :12] == 1.0)


def test_boolean_features_cast_to_int(sample_df):
    pipeline = build_preprocessing_pipeline()
    result = pipeline.fit_transform(sample_df)
    assert all(result[0, 12:] == 0)
    assert all(result[1, 12:] == 1)


def test_pipeline_feature_names_out(sample_df):
    pipeline = build_preprocessing_pipeline()
    pipeline.fit(sample_df)
    names = pipeline.get_feature_names_out()
    assert len(names) == 17
    for n in NUMERIC_FEATURES:
        assert n in names
    for b in BOOLEAN_FEATURES:
        assert b in names


def test_mvp_feature_names_excludes_firmographic():
    for name in FIRMOGRAPHIC_PLACEHOLDERS:
        assert name not in MVP_FEATURE_NAMES


def test_firmographic_placeholders_has_three_entries():
    assert len(FIRMOGRAPHIC_PLACEHOLDERS) == 3
    assert "company_size_bucket" in FIRMOGRAPHIC_PLACEHOLDERS
    assert "industry_match_icp" in FIRMOGRAPHIC_PLACEHOLDERS
    assert "job_title_seniority" in FIRMOGRAPHIC_PLACEHOLDERS
