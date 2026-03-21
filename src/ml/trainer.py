"""Train and evaluate an XGBoost model.

Accepts preprocessed DataFrames, wraps preprocessing + XGBoost in a single
sklearn Pipeline, evaluates on a holdout set, and returns a TrainResult
with metrics, feature importances, and the fitted pipeline.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.metrics import (
    f1_score,
    log_loss,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from xgboost import XGBClassifier


DEFAULT_HYPERPARAMETERS = {
    "n_estimators": 200,
    "max_depth": 6,
    "learning_rate": 0.1,
    "colsample_bytree": 0.8,
    "eval_metric": "logloss",
    "random_state": 42,
}


@dataclass
class TrainResult:
    model: Pipeline
    metrics: dict[str, float]
    feature_importance: dict[str, float]
    hyperparameters: dict
    feature_columns: list[str]


def _expected_calibration_error(y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10) -> float:
    """ECE using equal-frequency (quantile) bins."""
    quantiles = np.linspace(0, 100, n_bins + 1)
    bin_edges = np.percentile(y_prob, quantiles)
    bin_edges[0] = 0.0
    bin_edges[-1] = 1.0 + 1e-8

    ece = 0.0
    total = len(y_true)
    for i in range(n_bins):
        mask = (y_prob >= bin_edges[i]) & (y_prob < bin_edges[i + 1])
        if mask.sum() == 0:
            continue
        bin_acc = y_true[mask].mean()
        bin_conf = y_prob[mask].mean()
        ece += (mask.sum() / total) * abs(bin_acc - bin_conf)

    return float(ece)


def train_model(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_test: pd.DataFrame,
    y_test: pd.Series,
    preprocessing_pipeline: Pipeline,
    hyperparameters: dict | None = None,
) -> TrainResult:
    """Train XGBoost and evaluate on holdout set."""
    if y_train.nunique() < 2:
        raise ValueError("Training labels must contain both positive and negative examples")

    params = {**DEFAULT_HYPERPARAMETERS, **(hyperparameters or {})}

    # Compute class imbalance weight
    n_neg = int((y_train == False).sum())
    n_pos = int((y_train == True).sum())
    if n_pos > 0:
        params.setdefault("scale_pos_weight", n_neg / n_pos)

    clf = XGBClassifier(**params)

    model = Pipeline([
        *preprocessing_pipeline.steps,
        ("classifier", clf),
    ])

    model.fit(X_train, y_train)

    # Evaluate
    y_prob = model.predict_proba(X_test)[:, 1]
    y_pred = model.predict(X_test)
    y_test_arr = np.array(y_test, dtype=bool)

    metrics = {
        "auc_roc": float(roc_auc_score(y_test_arr, y_prob)),
        "precision": float(precision_score(y_test_arr, y_pred)),
        "recall": float(recall_score(y_test_arr, y_pred)),
        "f1": float(f1_score(y_test_arr, y_pred)),
        "log_loss": float(log_loss(y_test_arr, y_prob)),
        "calibration_error": _expected_calibration_error(y_test_arr, y_prob),
    }

    # Feature importance from XGBoost (mapped back to feature names)
    feature_names = list(model[:-1].get_feature_names_out())
    importances = clf.feature_importances_
    feature_importance = dict(zip(feature_names, [float(v) for v in importances]))

    return TrainResult(
        model=model,
        metrics=metrics,
        feature_importance=feature_importance,
        hyperparameters=params,
        feature_columns=list(X_train.columns),
    )
