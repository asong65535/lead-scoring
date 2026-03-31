"""SHAP-based per-prediction explainability.

Uses TreeExplainer for fast, exact SHAP values on XGBoost models.
Provides sample-specific feature contributions rather than global importance.
"""

from typing import Any

import numpy as np
import pandas as pd
import shap
from sklearn.pipeline import Pipeline


class Explainer:
    """Wraps a fitted sklearn Pipeline and produces per-sample SHAP explanations."""

    def __init__(self, model: Pipeline):
        self._model = model
        self._feature_names = list(model[:-1].get_feature_names_out())
        self._tree_explainer = shap.TreeExplainer(model.named_steps["classifier"])

    def _shap_values(self, df: pd.DataFrame) -> np.ndarray:
        """Compute SHAP values for preprocessed input.

        Returns array of shape (n_samples, n_features) for the positive class.
        """
        preprocessed = self._model[:-1].transform(df)
        sv = self._tree_explainer.shap_values(preprocessed)
        # TreeExplainer may return a list [neg_class, pos_class] or a single array
        if isinstance(sv, list):
            return sv[1]
        return sv

    def explain(
        self, df: pd.DataFrame, n: int = 5,
    ) -> list[dict[str, Any]]:
        """Explain a single-row DataFrame. Returns top N factors by abs SHAP value."""
        sv = self._shap_values(df)
        row_shap = sv[0]
        row_values = df.iloc[0]
        return self._format_factors(row_shap, row_values, n)

    def explain_batch(
        self, df: pd.DataFrame, n: int = 5,
    ) -> list[list[dict[str, Any]]]:
        """Explain multiple rows. Returns a list of factor lists, one per row."""
        sv = self._shap_values(df)
        results = []
        for i in range(len(df)):
            row_values = df.iloc[i]
            results.append(self._format_factors(sv[i], row_values, n))
        return results

    def _format_factors(
        self, shap_row: np.ndarray, feature_values: pd.Series, n: int,
    ) -> list[dict[str, Any]]:
        paired = sorted(
            zip(self._feature_names, shap_row),
            key=lambda x: abs(x[1]),
            reverse=True,
        )
        def _to_python(v: Any) -> Any:
            return v.item() if hasattr(v, "item") else v

        return [
            {
                "feature": name,
                "impact": float(val),
                "value": _to_python(feature_values.get(name)),
            }
            for name, val in paired[:n]
        ]
