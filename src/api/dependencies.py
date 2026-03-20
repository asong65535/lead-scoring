"""FastAPI dependency injection for scoring endpoints.

Three scopes:
- Model: application-scoped, lives on app.state
- FeatureComputer: engine-scoped, manages own sessions for reads
- Session: per-request, used for prediction writes
"""

from fastapi import Depends, Request
from sklearn.pipeline import Pipeline
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.exceptions import ModelNotLoadedError
from src.models.database import async_engine, get_session
from src.services.features.computer import FeatureComputer
from src.services.scoring import ScoringService

from config.settings import get_settings


def get_model(request: Request) -> tuple[Pipeline, str]:
    model = request.app.state.model
    if model is None:
        raise ModelNotLoadedError()
    version = request.app.state.model_version
    return model, version


def get_feature_computer() -> FeatureComputer:
    return FeatureComputer(async_engine)


async def get_scoring_service(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> ScoringService:
    model, version = get_model(request)
    feature_computer = get_feature_computer()
    settings = get_settings()
    return ScoringService(
        model=model,
        model_version=version,
        feature_computer=feature_computer,
        session=session,
        bucket_a=settings.model.bucket_a_threshold,
        bucket_b=settings.model.bucket_b_threshold,
        bucket_c=settings.model.bucket_c_threshold,
    )
