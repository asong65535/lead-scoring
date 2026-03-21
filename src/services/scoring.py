"""Scoring orchestrator — computes features, runs inference, logs predictions.

Receives a fitted sklearn Pipeline (model), a FeatureComputer (engine-scoped),
and a per-request AsyncSession (for writing Prediction rows).
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.exceptions import LeadNotFoundError
from src.models.prediction import Prediction
from src.services.features.computer import FeatureComputer


@dataclass
class ScoreResult:
    lead_id: UUID
    score: float
    bucket: str
    model_version: str
    top_factors: list[dict[str, Any]]
    scored_at: datetime


class ScoringService:
    def __init__(
        self,
        model: Pipeline,
        model_version: str,
        feature_computer: FeatureComputer,
        session: AsyncSession,
        bucket_a: float = 0.7,
        bucket_b: float = 0.4,
        bucket_c: float = 0.2,
    ):
        self._model = model
        self._model_version = model_version
        self._feature_computer = feature_computer
        self._session = session
        self._bucket_a = bucket_a
        self._bucket_b = bucket_b
        self._bucket_c = bucket_c

    @staticmethod
    def assign_bucket(
        score: float, bucket_a: float, bucket_b: float, bucket_c: float,
    ) -> str:
        if score >= bucket_a:
            return "A"
        if score >= bucket_b:
            return "B"
        if score >= bucket_c:
            return "C"
        return "D"

    @staticmethod
    def top_factors(
        feature_names: list[str],
        importances: np.ndarray,
        feature_values: dict[str, Any],
        n: int = 5,
    ) -> list[dict[str, Any]]:
        paired = sorted(
            zip(feature_names, importances),
            key=lambda x: abs(x[1]),
            reverse=True,
        )
        return [
            {
                "feature": name,
                "impact": float(imp),
                "value": feature_values.get(name),
            }
            for name, imp in paired[:n]
        ]

    def _get_feature_meta(self) -> tuple[list[str], np.ndarray]:
        feature_names = list(self._model[:-1].get_feature_names_out())
        importances = self._model.named_steps["classifier"].feature_importances_
        return feature_names, importances

    async def score_lead(self, lead_id: UUID) -> ScoreResult:
        try:
            features = await self._feature_computer.compute(lead_id)
        except NoResultFound:
            raise LeadNotFoundError(lead_id)

        feature_names, importances = self._get_feature_meta()
        df = pd.DataFrame([{k: features[k] for k in feature_names}])
        proba = float(self._model.predict_proba(df)[0, 1])

        bucket = self.assign_bucket(
            proba, self._bucket_a, self._bucket_b, self._bucket_c,
        )
        factors = self.top_factors(feature_names, importances, features)
        scored_at = datetime.now(timezone.utc)

        snapshot = {k: features[k] for k in feature_names}
        pred = Prediction(
            lead_id=lead_id,
            score=proba,
            bucket=bucket,
            model_version=self._model_version,
            feature_snapshot=snapshot,
            top_factors=factors,
            scored_at=scored_at,
        )
        self._session.add(pred)
        await self._session.commit()

        return ScoreResult(
            lead_id=lead_id,
            score=proba,
            bucket=bucket,
            model_version=self._model_version,
            top_factors=factors,
            scored_at=scored_at,
        )

    async def score_leads(
        self, lead_ids: list[UUID],
    ) -> tuple[list[ScoreResult], list[UUID]]:
        feature_dicts = await self._feature_computer.compute_batch(lead_ids)

        found_ids = {d["lead_id"] for d in feature_dicts}
        missing_ids = [lid for lid in lead_ids if lid not in found_ids]

        if not feature_dicts:
            return [], missing_ids

        feature_names, importances = self._get_feature_meta()

        rows = [{k: d[k] for k in feature_names} for d in feature_dicts]
        df = pd.DataFrame(rows)
        probas = self._model.predict_proba(df)[:, 1]

        results = []
        scored_at = datetime.now(timezone.utc)

        for i, feat_dict in enumerate(feature_dicts):
            lid = feat_dict["lead_id"]
            proba = float(probas[i])
            bucket = self.assign_bucket(
                proba, self._bucket_a, self._bucket_b, self._bucket_c,
            )
            factors = self.top_factors(feature_names, importances, feat_dict)
            snapshot = {k: feat_dict[k] for k in feature_names}

            pred = Prediction(
                lead_id=lid,
                score=proba,
                bucket=bucket,
                model_version=self._model_version,
                feature_snapshot=snapshot,
                top_factors=factors,
                scored_at=scored_at,
            )
            self._session.add(pred)

            results.append(ScoreResult(
                lead_id=lid,
                score=proba,
                bucket=bucket,
                model_version=self._model_version,
                top_factors=factors,
                scored_at=scored_at,
            ))

        await self._session.commit()
        return results, missing_ids
