"""CLI entry point for automated model retraining.

Usage:
    poetry run python scripts/retrain.py                    # retrain with defaults
    poetry run python scripts/retrain.py --tune             # tune then retrain
    poetry run python scripts/retrain.py --force            # skip comparison gate
    poetry run python scripts/retrain.py --dry-run          # train + compare only

Intended to be called via cron for weekly retraining.
"""

import argparse
import asyncio
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from config.settings import Settings, get_settings
from src.ml.alerts import send_alert
from src.ml.comparison import compare_models, ComparisonResult
from src.ml.dataset import build_training_dataset
from src.ml.drift import compute_feature_baselines, detect_drift, DriftResult
from src.ml.preprocessing import (
    build_preprocessing_pipeline,
    MVP_FEATURE_NAMES,
    NUMERIC_FEATURES,
    BOOLEAN_FEATURES,
)
from src.ml.serialization import (
    get_existing_versions,
    next_version,
    register_model,
    save_model,
)
from src.ml.trainer import train_model
from src.ml.tuning import tune_hyperparameters
from src.models.model_registry import ModelRegistry
from src.models.prediction import Prediction
from src.models.retraining_run import RetrainingRun

logger = structlog.get_logger()


def determine_triggered_by(force: bool) -> str:
    """Determine the triggered_by value based on CLI flags."""
    if force:
        return "force"
    return "manual"


async def get_active_model_info(engine: AsyncEngine) -> dict | None:
    """Query the active model's version and metrics from the registry."""
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        result = await session.execute(
            select(ModelRegistry).where(ModelRegistry.is_active.is_(True)).limit(1)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return {
            "version": row.version,
            "metrics": row.metrics,
            "artifact_path": row.artifact_path,
        }


async def run_drift_detection(
    engine: AsyncEngine,
    model_version: str,
    settings: Settings,
) -> DriftResult | None:
    """Query recent predictions and run drift detection."""
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    window_start = datetime.now(timezone.utc) - timedelta(days=settings.retrain.drift_window_days)

    async with session_factory() as session:
        result = await session.execute(
            select(Prediction.feature_snapshot, Prediction.score)
            .where(Prediction.model_version == model_version)
            .where(Prediction.scored_at >= window_start)
        )
        rows = result.all()

    if len(rows) < settings.retrain.min_drift_samples:
        logger.info("drift_skipped", reason="insufficient recent predictions", count=len(rows))
        return None

    recent_snapshots = [row.feature_snapshot for row in rows if row.feature_snapshot]
    recent_scores = [float(row.score) for row in rows]

    # Load baselines from most recent successful retraining run
    async with session_factory() as session:
        result = await session.execute(
            select(RetrainingRun.feature_baselines)
            .where(RetrainingRun.run_status == "success")
            .order_by(RetrainingRun.started_at.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()

    if row is None:
        logger.info("drift_skipped", reason="no baseline from previous retrain run")
        return None

    return detect_drift(
        feature_baselines=row,
        recent_snapshots=recent_snapshots,
        numeric_features=NUMERIC_FEATURES,
        boolean_features=BOOLEAN_FEATURES,
        psi_threshold=settings.retrain.drift_psi_threshold,
        min_samples=settings.retrain.min_drift_samples,
        recent_scores=recent_scores,
    )


def compute_training_data_stats(train_df, test_df) -> dict:
    """Compute summary statistics for the training data."""
    return {
        "train_rows": len(train_df),
        "test_rows": len(test_df),
        "train_positive_rate": float(train_df["converted"].mean()),
        "test_positive_rate": float(test_df["converted"].mean()),
        "total_rows": len(train_df) + len(test_df),
    }


async def trigger_hot_reload(app_url: str = "http://app:8000") -> bool:
    """POST to the admin reload endpoint to hot-swap the model."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(f"{app_url}/admin/reload-model")
            if response.status_code == 200:
                logger.info("hot_reload_success", response=response.json())
                return True
            else:
                logger.warning("hot_reload_failed", status_code=response.status_code)
                return False
    except Exception as exc:
        logger.warning("hot_reload_unreachable", error=str(exc))
        return False


async def record_run(
    engine: AsyncEngine,
    run_status: str,
    candidate_version: str,
    active_version_before: str | None,
    promoted: bool,
    current_metrics: dict | None,
    candidate_metrics: dict | None,
    metric_deltas: dict,
    comparison_reason: str,
    drift_result: DriftResult | None,
    feature_baselines: dict,
    training_data_stats: dict,
    hyperparameters: dict,
    triggered_by: str,
    duration_seconds: float,
    error_message: str | None,
    started_at: datetime,
) -> UUID:
    """Insert a retraining_runs row."""
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        async with session.begin():
            run = RetrainingRun(
                run_status=run_status,
                candidate_version=candidate_version,
                active_version_before=active_version_before,
                promoted=promoted,
                current_metrics=current_metrics,
                candidate_metrics=candidate_metrics,
                metric_deltas=metric_deltas,
                comparison_reason=comparison_reason,
                drift_result=_drift_to_dict(drift_result),
                feature_baselines=feature_baselines,
                training_data_stats=training_data_stats,
                hyperparameters=hyperparameters,
                triggered_by=triggered_by,
                duration_seconds=duration_seconds,
                error_message=error_message,
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
            )
            session.add(run)
        return run.id


def _drift_to_dict(drift_result: DriftResult | None) -> dict | None:
    if drift_result is None:
        return None
    return {
        "has_significant_drift": drift_result.has_significant_drift,
        "feature_drift": drift_result.feature_drift,
        "drifted_features": drift_result.drifted_features,
        "prediction_drift": drift_result.prediction_drift,
        "summary": drift_result.summary,
    }


async def execute_retrain(
    engine: AsyncEngine,
    tune: bool,
    force: bool,
    dry_run: bool,
    settings: Settings,
) -> dict:
    """Execute the full retraining pipeline. Returns a summary dict."""
    started_at = datetime.now(timezone.utc)
    start_mono = time.monotonic()
    triggered_by = determine_triggered_by(force)

    # Step 1: Load active model info
    active_info = await get_active_model_info(engine)
    active_version = active_info["version"] if active_info else None
    active_metrics = active_info["metrics"] if active_info else None

    # Step 2: Drift detection
    drift_result = None
    if active_version:
        drift_result = await run_drift_detection(engine, active_version, settings)
        if drift_result and drift_result.has_significant_drift:
            logger.warning("drift_detected", summary=drift_result.summary)
            await send_alert(
                "drift.detected",
                {
                    "model_version": active_version,
                    "drifted_features": drift_result.drifted_features,
                    "feature_drift": drift_result.feature_drift,
                    "summary": drift_result.summary,
                },
                webhook_url=settings.retrain.webhook_url,
            )

    # Step 3: Build training dataset
    train_df, test_df = await build_training_dataset(engine)
    training_data_stats = compute_training_data_stats(train_df, test_df)

    X_train = train_df[MVP_FEATURE_NAMES]
    y_train = train_df["converted"]
    X_test = test_df[MVP_FEATURE_NAMES]
    y_test = test_df["converted"]

    # Compute feature baselines from training data
    train_feature_dicts = X_train.to_dict(orient="records")
    feature_baselines = compute_feature_baselines(
        train_feature_dicts,
        numeric_features=NUMERIC_FEATURES,
        boolean_features=BOOLEAN_FEATURES,
    )

    # Step 4: Train
    pipeline = build_preprocessing_pipeline()
    hyperparameters = None
    if tune:
        hyperparameters = tune_hyperparameters(X_train, y_train, pipeline)
        pipeline = build_preprocessing_pipeline()

    result = train_model(X_train, y_train, X_test, y_test, pipeline, hyperparameters)

    # Step 5: Compare
    comparison = compare_models(
        current_metrics=active_metrics,
        candidate_metrics=result.metrics,
        primary_metric=settings.retrain.primary_metric,
        max_relative_drop=settings.retrain.max_relative_drop,
        max_calibration_increase=settings.retrain.max_calibration_increase,
    )

    should_promote = comparison.should_promote or force

    # Step 6: Determine version
    existing = await get_existing_versions(engine)
    version = next_version(existing)

    duration = time.monotonic() - start_mono

    if dry_run:
        run_status = "success" if comparison.should_promote else "blocked"
        await record_run(
            engine=engine,
            run_status=run_status,
            candidate_version=version,
            active_version_before=active_version,
            promoted=False,
            current_metrics=active_metrics,
            candidate_metrics=result.metrics,
            metric_deltas=comparison.metric_deltas,
            comparison_reason=comparison.reason + " (dry run)",
            drift_result=drift_result,
            feature_baselines=feature_baselines,
            training_data_stats=training_data_stats,
            hyperparameters=result.hyperparameters,
            triggered_by=triggered_by,
            duration_seconds=duration,
            error_message=None,
            started_at=started_at,
        )
        return {
            "promoted": False,
            "candidate_version": version,
            "run_status": run_status,
            "comparison": comparison,
            "dry_run": True,
        }

    # Save artifact
    artifact_path = save_model(
        result.model, version,
        result.metrics, result.hyperparameters,
        result.feature_columns,
    )

    # Register
    await register_model(
        engine, version, artifact_path,
        result.metrics, result.hyperparameters,
        result.feature_columns, set_active=should_promote,
    )

    # Hot reload if promoted
    if should_promote:
        await trigger_hot_reload()
        await send_alert(
            "retrain.success",
            {
                "version": version,
                "metrics": result.metrics,
                "metric_deltas": comparison.metric_deltas,
                "active_version_before": active_version,
            },
            webhook_url=settings.retrain.webhook_url,
        )
        run_status = "success"
    else:
        await send_alert(
            "retrain.blocked",
            {
                "version": version,
                "metrics": result.metrics,
                "metric_deltas": comparison.metric_deltas,
                "reason": comparison.reason,
                "active_version": active_version,
            },
            webhook_url=settings.retrain.webhook_url,
        )
        run_status = "blocked"

    # Record run
    await record_run(
        engine=engine,
        run_status=run_status,
        candidate_version=version,
        active_version_before=active_version,
        promoted=should_promote,
        current_metrics=active_metrics,
        candidate_metrics=result.metrics,
        metric_deltas=comparison.metric_deltas,
        comparison_reason=comparison.reason,
        drift_result=drift_result,
        feature_baselines=feature_baselines,
        training_data_stats=training_data_stats,
        hyperparameters=result.hyperparameters,
        triggered_by=triggered_by,
        duration_seconds=duration,
        error_message=None,
        started_at=started_at,
    )

    return {
        "promoted": should_promote,
        "candidate_version": version,
        "run_status": run_status,
        "comparison": comparison,
        "dry_run": False,
    }


async def main(
    tune: bool = False,
    force: bool = False,
    dry_run: bool = False,
) -> None:
    from src.models.database import async_engine

    settings = get_settings()

    try:
        summary = await execute_retrain(
            engine=async_engine,
            tune=tune,
            force=force,
            dry_run=dry_run,
            settings=settings,
        )

        comparison = summary["comparison"]
        print(f"\n{'=' * 50}")
        print(f"Retrain {'(dry run) ' if dry_run else ''}complete")
        print(f"{'=' * 50}")
        print(f"  Candidate: {summary['candidate_version']}")
        print(f"  Status: {summary['run_status']}")
        print(f"  Promoted: {summary['promoted']}")
        print(f"  Reason: {comparison.reason}")
        if comparison.candidate_metrics:
            print(f"\n  Candidate metrics:")
            for name, value in comparison.candidate_metrics.items():
                print(f"    {name}: {value:.4f}")
        if comparison.metric_deltas:
            print(f"\n  Metric deltas:")
            for name, delta in comparison.metric_deltas.items():
                print(f"    {name}: {delta['absolute']:+.4f} ({delta['relative']:+.1%})")

    except Exception as exc:
        logger.error("retrain_failed", error=str(exc), traceback=traceback.format_exc())
        await send_alert(
            "retrain.failed",
            {"error": str(exc), "traceback": traceback.format_exc()},
            webhook_url=settings.retrain.webhook_url,
        )

        await record_run(
            engine=async_engine,
            run_status="failed",
            candidate_version="unknown",
            active_version_before=None,
            promoted=False,
            current_metrics=None,
            candidate_metrics=None,
            metric_deltas={},
            comparison_reason="",
            drift_result=None,
            feature_baselines={},
            training_data_stats={},
            hyperparameters={},
            triggered_by=determine_triggered_by(force),
            duration_seconds=0,
            error_message=str(exc),
            started_at=datetime.now(timezone.utc),
        )
        raise
    finally:
        await async_engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Retrain lead scoring model")
    parser.add_argument("--tune", action="store_true", help="Run hyperparameter tuning")
    parser.add_argument("--force", action="store_true", help="Skip comparison gate, promote regardless")
    parser.add_argument("--dry-run", action="store_true", help="Train and compare but don't register or promote")
    args = parser.parse_args()

    asyncio.run(main(tune=args.tune, force=args.force, dry_run=args.dry_run))
