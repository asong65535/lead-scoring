"""Optional hyperparameter tuning via randomized search.

Standalone module — not called by the default training flow.
Use via `scripts/train.py --tune` or directly from Phase 9 retraining.
"""

import pandas as pd
from sklearn.model_selection import RandomizedSearchCV, StratifiedKFold
from sklearn.pipeline import Pipeline
from xgboost import XGBClassifier

DEFAULT_PARAM_GRID = {
    "n_estimators": [100, 200, 300],
    "max_depth": [4, 6, 8],
    "learning_rate": [0.05, 0.1, 0.2],
}


def tune_hyperparameters(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    preprocessing_pipeline: Pipeline,
    param_grid: dict | None = None,
    cv_folds: int = 5,
    n_iter: int = 20,
) -> dict:
    """Find best XGBoost hyperparameters via randomized search.

    Returns a dict of best hyperparameters suitable for passing to train_model().
    """
    grid = param_grid or DEFAULT_PARAM_GRID

    # Prefix grid keys for Pipeline parameter naming
    prefixed_grid = {f"classifier__{k}": v for k, v in grid.items()}

    model = Pipeline([
        *preprocessing_pipeline.steps,
        ("classifier", XGBClassifier(eval_metric="logloss", random_state=42)),
    ])

    search = RandomizedSearchCV(
        model,
        prefixed_grid,
        n_iter=n_iter,
        scoring="roc_auc",
        cv=StratifiedKFold(n_splits=cv_folds, shuffle=True, random_state=42),
        n_jobs=-1,
        refit=False,
        random_state=42,
    )

    search.fit(X_train, y_train)

    # Strip 'classifier__' prefix from best params
    best = {k.replace("classifier__", ""): v for k, v in search.best_params_.items()}
    return best
