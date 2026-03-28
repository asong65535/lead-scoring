"""Tests for SHAP-based per-prediction explainability."""

import numpy as np
import pandas as pd
import pytest
from sklearn.pipeline import Pipeline

from src.ml.preprocessing import (
    build_preprocessing_pipeline,
    MVP_FEATURE_NAMES,
    NUMERIC_FEATURES,
    BOOLEAN_FEATURES,
)
from src.ml.trainer import train_model


@pytest.fixture(scope="module")
def trained_pipeline():
    """Train a small model for explainer tests."""
    rng = np.random.default_rng(42)
    n = 200
    data = {}
    for name in NUMERIC_FEATURES:
        data[name] = rng.uniform(0, 10, size=n)
    for name in BOOLEAN_FEATURES:
        data[name] = rng.choice([True, False], size=n)

    df = pd.DataFrame(data)
    # Label correlated with first numeric feature for a learnable signal
    y = (df[NUMERIC_FEATURES[0]] > 5).astype(bool)
    df_train, df_test = df[:150], df[150:]
    y_train, y_test = y[:150], y[150:]

    preprocessing = build_preprocessing_pipeline()
    result = train_model(df_train, y_train, df_test, y_test, preprocessing)
    return result.model


class TestExplainer:
    def test_explain_single_returns_per_feature_shap_values(self, trained_pipeline):
        from src.ml.explainer import Explainer

        explainer = Explainer(trained_pipeline)

        # Build a single sample
        rng = np.random.default_rng(99)
        sample = {}
        for name in NUMERIC_FEATURES:
            sample[name] = float(rng.uniform(0, 10))
        for name in BOOLEAN_FEATURES:
            sample[name] = True
        df = pd.DataFrame([sample])

        factors = explainer.explain(df, n=5)

        assert len(factors) == 5
        for f in factors:
            assert "feature" in f
            assert "impact" in f
            assert "value" in f
            assert isinstance(f["impact"], float)

    def test_explain_impacts_are_sample_specific(self, trained_pipeline):
        """Two different samples should produce different SHAP impacts."""
        from src.ml.explainer import Explainer

        explainer = Explainer(trained_pipeline)

        rng = np.random.default_rng(123)
        samples = []
        for _ in range(2):
            sample = {}
            for name in NUMERIC_FEATURES:
                sample[name] = float(rng.uniform(0, 10))
            for name in BOOLEAN_FEATURES:
                sample[name] = bool(rng.choice([True, False]))
            samples.append(sample)

        df1 = pd.DataFrame([samples[0]])
        df2 = pd.DataFrame([samples[1]])

        factors1 = explainer.explain(df1, n=5)
        factors2 = explainer.explain(df2, n=5)

        # At least one impact should differ between the two samples
        impacts1 = {f["feature"]: f["impact"] for f in factors1}
        impacts2 = {f["feature"]: f["impact"] for f in factors2}
        shared = set(impacts1) & set(impacts2)
        differs = any(
            abs(impacts1[k] - impacts2[k]) > 1e-6 for k in shared
        )
        assert differs, "SHAP values should be sample-specific, not global"

    def test_explain_batch_returns_one_explanation_per_row(self, trained_pipeline):
        from src.ml.explainer import Explainer

        explainer = Explainer(trained_pipeline)

        rng = np.random.default_rng(77)
        rows = []
        for _ in range(3):
            row = {}
            for name in NUMERIC_FEATURES:
                row[name] = float(rng.uniform(0, 10))
            for name in BOOLEAN_FEATURES:
                row[name] = bool(rng.choice([True, False]))
            rows.append(row)
        df = pd.DataFrame(rows)

        batch_factors = explainer.explain_batch(df, n=3)

        assert len(batch_factors) == 3
        for factors in batch_factors:
            assert len(factors) == 3

    def test_explain_sorted_by_abs_impact(self, trained_pipeline):
        from src.ml.explainer import Explainer

        explainer = Explainer(trained_pipeline)

        rng = np.random.default_rng(55)
        sample = {}
        for name in NUMERIC_FEATURES:
            sample[name] = float(rng.uniform(0, 10))
        for name in BOOLEAN_FEATURES:
            sample[name] = True
        df = pd.DataFrame([sample])

        factors = explainer.explain(df, n=len(NUMERIC_FEATURES) + len(BOOLEAN_FEATURES))

        abs_impacts = [abs(f["impact"]) for f in factors]
        assert abs_impacts == sorted(abs_impacts, reverse=True)
