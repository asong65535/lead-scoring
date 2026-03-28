"""PSI-based drift detection for features and prediction distributions.

Compares recent prediction feature snapshots against training-time baselines.
Uses Population Stability Index (PSI) per numeric feature and true-rate shift
for boolean features.
"""

from dataclasses import dataclass, field

import numpy as np


@dataclass
class DriftResult:
    has_significant_drift: bool
    feature_drift: dict[str, float]
    drifted_features: list[str]
    prediction_drift: dict
    summary: str


def compute_psi(
    baseline: np.ndarray | list,
    recent: np.ndarray | list,
    n_bins: int = 10,
) -> float:
    """Compute Population Stability Index between two distributions.

    Uses quantile-based binning from the baseline distribution.
    Returns 0.0 if either array is empty.
    """
    baseline = np.asarray(baseline, dtype=float)
    recent = np.asarray(recent, dtype=float)

    if len(baseline) == 0 or len(recent) == 0:
        return 0.0

    quantiles = np.linspace(0, 100, n_bins + 1)
    bin_edges = np.percentile(baseline, quantiles)
    bin_edges[0] = -np.inf
    bin_edges[-1] = np.inf

    bin_edges = np.unique(bin_edges)
    if len(bin_edges) < 2:
        return 0.0

    baseline_counts = np.histogram(baseline, bins=bin_edges)[0]
    recent_counts = np.histogram(recent, bins=bin_edges)[0]

    eps = 1e-6
    baseline_pct = baseline_counts / len(baseline) + eps
    recent_pct = recent_counts / len(recent) + eps

    psi = float(np.sum((recent_pct - baseline_pct) * np.log(recent_pct / baseline_pct)))
    return max(psi, 0.0)


def compute_feature_baselines(
    feature_dicts: list[dict],
    numeric_features: list[str],
    boolean_features: list[str],
) -> dict:
    """Summarize training feature distributions for future drift comparison.

    For numeric features: stores mean, std, and raw values (for PSI binning).
    For boolean features: stores true_rate.
    """
    baselines = {}

    for feat in numeric_features:
        values = [d[feat] for d in feature_dicts if feat in d and d[feat] is not None]
        if values:
            arr = np.asarray(values, dtype=float)
            baselines[feat] = {
                "mean": float(np.mean(arr)),
                "std": float(np.std(arr)),
                "values": [float(v) for v in arr],
            }

    for feat in boolean_features:
        values = [d[feat] for d in feature_dicts if feat in d and d[feat] is not None]
        if values:
            true_count = sum(1 for v in values if v)
            baselines[feat] = {
                "true_rate": true_count / len(values),
                "count": len(values),
            }

    return baselines


def detect_drift(
    feature_baselines: dict,
    recent_snapshots: list[dict],
    numeric_features: list[str],
    boolean_features: list[str],
    psi_threshold: float = 0.2,
    min_samples: int = 50,
    recent_scores: list[float] | None = None,
) -> DriftResult:
    """Detect feature-level and prediction-level drift.

    Computes PSI for each numeric feature and true-rate shift for booleans.
    Returns DriftResult with drifted features flagged.
    """
    if len(recent_snapshots) < min_samples:
        return DriftResult(
            has_significant_drift=False,
            feature_drift={},
            drifted_features=[],
            prediction_drift={},
            summary=f"Insufficient samples ({len(recent_snapshots)} < {min_samples})",
        )

    feature_drift = {}
    drifted_features = []

    for feat in numeric_features:
        baseline_info = feature_baselines.get(feat)
        if baseline_info is None or "values" not in baseline_info:
            continue
        recent_values = [d[feat] for d in recent_snapshots if feat in d and d[feat] is not None]
        if len(recent_values) < min_samples:
            continue
        psi = compute_psi(baseline_info["values"], recent_values)
        feature_drift[feat] = psi
        if psi > psi_threshold:
            drifted_features.append(feat)

    for feat in boolean_features:
        baseline_info = feature_baselines.get(feat)
        if baseline_info is None or "true_rate" not in baseline_info:
            continue
        recent_values = [d[feat] for d in recent_snapshots if feat in d and d[feat] is not None]
        if len(recent_values) < min_samples:
            continue
        recent_rate = sum(1 for v in recent_values if v) / len(recent_values)
        shift = abs(recent_rate - baseline_info["true_rate"])
        feature_drift[feat] = shift
        if shift > psi_threshold:
            drifted_features.append(feat)

    prediction_drift = {}
    baseline_scores = feature_baselines.get("_prediction_scores")
    if baseline_scores is not None and recent_scores is not None and len(recent_scores) >= min_samples:
        baseline_arr = np.asarray(baseline_scores, dtype=float)
        recent_arr = np.asarray(recent_scores, dtype=float)
        prediction_drift = {
            "prediction_drift": {
                "baseline_mean": float(np.mean(baseline_arr)),
                "recent_mean": float(np.mean(recent_arr)),
                "mean_shift": float(np.mean(recent_arr) - np.mean(baseline_arr)),
                "baseline_std": float(np.std(baseline_arr)),
                "recent_std": float(np.std(recent_arr)),
                "psi": compute_psi(baseline_arr, recent_arr),
            }
        }

    has_drift = len(drifted_features) > 0
    if has_drift:
        summary = f"Significant drift in {len(drifted_features)} feature(s): {', '.join(drifted_features)}"
    else:
        summary = f"No significant drift detected across {len(feature_drift)} features"

    return DriftResult(
        has_significant_drift=has_drift,
        feature_drift=feature_drift,
        drifted_features=drifted_features,
        prediction_drift=prediction_drift,
        summary=summary,
    )
