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


def test_boolean_features_pass_through(sample_df):
    """Booleans pass through via passthrough transformer (no explicit FunctionTransformer).

    sklearn's ColumnTransformer coerces bools to float64 when combining with
    numeric columns, so the output values are 0.0/1.0. The key point is that
    no custom bool-to-int transformer is needed — passthrough handles it.
    """
    pipeline = build_preprocessing_pipeline()
    result = pipeline.fit_transform(sample_df)
    assert all(result[0, 12:] == 0.0)
    assert all(result[1, 12:] == 1.0)
    # Verify no explicit bool transformer in the pipeline
    preprocessor = pipeline.named_steps["preprocessor"]
    for name, transformer, _ in preprocessor.transformers:
        assert transformer == "passthrough", (
            f"Transformer '{name}' should be passthrough, got {transformer}"
        )


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
