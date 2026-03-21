"""Preprocessing pipeline for ML features.

Builds a sklearn ColumnTransformer that handles 17 MVP features:
- 12 numeric features → pass-through (XGBoost handles natively)
- 5 boolean features → pass-through (XGBoost handles natively)

Firmographic features (company_size_bucket, industry_match_icp, job_title_seniority)
are excluded from MVP training — they always return YAML defaults. They rejoin
when CRM data populates them (Phase 7+).
"""

from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline

FIRMOGRAPHIC_PLACEHOLDERS = frozenset({
    "company_size_bucket",
    "industry_match_icp",
    "job_title_seniority",
})

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

MVP_FEATURE_NAMES = NUMERIC_FEATURES + BOOLEAN_FEATURES


def build_preprocessing_pipeline() -> Pipeline:
    """Build sklearn Pipeline for 17 MVP features."""
    transformer = ColumnTransformer(
        transformers=[
            ("numeric", "passthrough", NUMERIC_FEATURES),
            ("boolean", "passthrough", BOOLEAN_FEATURES),
        ],
        verbose_feature_names_out=False,
    )
    return Pipeline([("preprocessor", transformer)])
