"""Compare candidate model metrics against the active model.

Returns a ComparisonResult with a promote/block decision, reason,
and per-metric deltas.
"""

from dataclasses import dataclass


@dataclass
class ComparisonResult:
    should_promote: bool
    reason: str
    current_metrics: dict | None
    candidate_metrics: dict
    metric_deltas: dict


def compare_models(
    current_metrics: dict | None,
    candidate_metrics: dict,
    primary_metric: str = "auc_roc",
    max_relative_drop: float = 0.05,
    max_calibration_increase: float = 0.05,
) -> ComparisonResult:
    """Compare candidate against current model metrics.

    Returns ComparisonResult with should_promote=True if the candidate
    passes all gates. If current_metrics is None (first train), always promotes.
    """
    if current_metrics is None:
        return ComparisonResult(
            should_promote=True,
            reason="No active model — promoting first candidate",
            current_metrics=None,
            candidate_metrics=candidate_metrics,
            metric_deltas={},
        )

    # Compute deltas for all shared metrics
    metric_deltas = {}
    for key in candidate_metrics:
        if key in current_metrics and current_metrics[key] != 0:
            absolute = candidate_metrics[key] - current_metrics[key]
            relative = absolute / abs(current_metrics[key])
            metric_deltas[key] = {"absolute": absolute, "relative": relative}

    # Gate 1: primary metric (higher is better)
    current_primary = current_metrics.get(primary_metric, 0)
    candidate_primary = candidate_metrics.get(primary_metric, 0)
    if current_primary > 0:
        relative_drop = (current_primary - candidate_primary) / current_primary
        if relative_drop > max_relative_drop:
            return ComparisonResult(
                should_promote=False,
                reason=(
                    f"{primary_metric} dropped {relative_drop:.1%} "
                    f"(from {current_primary:.4f} to {candidate_primary:.4f}), "
                    f"exceeds {max_relative_drop:.1%} threshold"
                ),
                current_metrics=current_metrics,
                candidate_metrics=candidate_metrics,
                metric_deltas=metric_deltas,
            )

    # Gate 2: calibration error (lower is better)
    current_cal = current_metrics.get("calibration_error")
    candidate_cal = candidate_metrics.get("calibration_error")
    if current_cal is not None and candidate_cal is not None:
        cal_increase = candidate_cal - current_cal
        if cal_increase > max_calibration_increase:
            return ComparisonResult(
                should_promote=False,
                reason=(
                    f"calibration_error increased by {cal_increase:.4f} "
                    f"(from {current_cal:.4f} to {candidate_cal:.4f}), "
                    f"exceeds {max_calibration_increase:.4f} threshold"
                ),
                current_metrics=current_metrics,
                candidate_metrics=candidate_metrics,
                metric_deltas=metric_deltas,
            )

    return ComparisonResult(
        should_promote=True,
        reason="All metric gates passed",
        current_metrics=current_metrics,
        candidate_metrics=candidate_metrics,
        metric_deltas=metric_deltas,
    )
