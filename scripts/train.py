"""CLI entry point for model training.

Usage:
    poetry run python scripts/train.py                  # train with defaults
    poetry run python scripts/train.py --tune            # tune then train
    poetry run python scripts/train.py --set-active      # train and deploy
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add project root to path so imports work when run as script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.ext.asyncio import create_async_engine

from config.settings import get_settings
from src.ml.dataset import build_training_dataset
from src.ml.preprocessing import build_preprocessing_pipeline, MVP_FEATURE_NAMES
from src.ml.trainer import train_model
from src.ml.tuning import tune_hyperparameters
from src.ml.serialization import save_model, register_model, next_version, get_existing_versions


async def main(tune: bool = False, set_active: bool = False) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database.url)

    try:
        print("Building training dataset...")
        train_df, test_df = await build_training_dataset(engine)
        print(f"  Train: {len(train_df)} rows, Test: {len(test_df)} rows")
        print(f"  Train conversion rate: {train_df['converted'].mean():.1%}")
        print(f"  Test conversion rate: {test_df['converted'].mean():.1%}")

        X_train = train_df[MVP_FEATURE_NAMES]
        y_train = train_df["converted"]
        X_test = test_df[MVP_FEATURE_NAMES]
        y_test = test_df["converted"]

        pipeline = build_preprocessing_pipeline()
        hyperparameters = None

        if tune:
            print("\nTuning hyperparameters...")
            hyperparameters = tune_hyperparameters(X_train, y_train, pipeline)
            print(f"  Best params: {hyperparameters}")
            # Rebuild pipeline since tuning consumed it
            pipeline = build_preprocessing_pipeline()

        print("\nTraining model...")
        result = train_model(X_train, y_train, X_test, y_test, pipeline, hyperparameters)

        # Determine version
        existing = await get_existing_versions(engine)
        version = next_version(existing)

        # Save artifact
        artifact_path = save_model(
            result.model, version,
            result.metrics, result.hyperparameters,
            result.feature_columns,
        )

        # Register in DB
        model_id = await register_model(
            engine, version, artifact_path,
            result.metrics, result.hyperparameters,
            result.feature_columns, set_active=set_active,
        )

        # Print summary
        print(f"\n{'=' * 50}")
        print(f"Model {version} trained successfully")
        print(f"{'=' * 50}")
        print(f"  Artifact: {artifact_path}")
        print(f"  Registry ID: {model_id}")
        print(f"  Active: {set_active}")
        print(f"\n  Metrics:")
        for name, value in result.metrics.items():
            print(f"    {name}: {value:.4f}")
        print(f"\n  Top 5 features:")
        sorted_features = sorted(result.feature_importance.items(), key=lambda x: x[1], reverse=True)
        for name, importance in sorted_features[:5]:
            print(f"    {name}: {importance:.4f}")

    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train lead scoring model")
    parser.add_argument("--tune", action="store_true", help="Run hyperparameter tuning before training")
    parser.add_argument("--set-active", action="store_true", help="Set trained model as active")
    args = parser.parse_args()

    asyncio.run(main(tune=args.tune, set_active=args.set_active))
