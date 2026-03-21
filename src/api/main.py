"""Lead Scoring API — application factory and lifespan management."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from config.settings import get_settings
from src.api.exceptions import (
    FeatureComputationError,
    LeadNotFoundError,
    ModelNotLoadedError,
)
from src.api.middleware.auth import AuthMiddleware
from src.api.middleware.logging import LoggingMiddleware, configure_logging
from src.api.middleware.rate_limit import RateLimitMiddleware
from src.api.middleware.request_id import RequestIDMiddleware
from src.api.routes import health
from src.api.routes import scoring
from src.api.routes import webhooks
from src.api.routes import admin
from src.ml.serialization import load_model
from src.models.database import async_engine
from src.models.model_registry import ModelRegistry

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    configure_logging(debug=settings.debug)

    logger.info(
        "app_starting",
        app=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
    )

    # Load active model from registry
    session_factory = async_sessionmaker(
        bind=async_engine, class_=AsyncSession, expire_on_commit=False,
    )
    async with session_factory() as session:
        result = await session.execute(
            select(ModelRegistry).where(ModelRegistry.is_active == True)  # noqa: E712
        )
        active_model = result.scalar_one_or_none()

    if active_model:
        artifact_path = Path(active_model.artifact_path)
        if artifact_path.exists():
            app.state.model = load_model(artifact_path)
            app.state.model_version = active_model.version
            logger.info("model_loaded", version=active_model.version)
        else:
            app.state.model = None
            app.state.model_version = None
            logger.warning(
                "model_artifact_missing",
                version=active_model.version,
                path=str(artifact_path),
            )
    else:
        app.state.model = None
        app.state.model_version = None
        logger.warning("no_active_model_in_registry")

    app.state.settings = settings

    yield

    logger.info("app_shutting_down")
    await async_engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="ML-powered lead scoring system with CRM integration",
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        lifespan=lifespan,
    )

    # Middleware (order matters — outermost first in execution, last added = outermost)
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(RateLimitMiddleware,
        max_requests=settings.rate_limit_requests,
        window_seconds=settings.rate_limit_window_seconds,
    )
    if settings.auth_enabled:
        app.add_middleware(AuthMiddleware,
            engine=async_engine,
            exempt_paths=settings.auth_exempt_paths,
        )

    # Routers
    app.include_router(health.router, tags=["Health"])
    app.include_router(scoring.router, prefix="/score", tags=["Scoring"])
    app.include_router(webhooks.router, prefix="/webhooks", tags=["Webhooks"])
    app.include_router(admin.router, prefix="/admin", tags=["Admin"])

    # Exception handlers
    @app.exception_handler(LeadNotFoundError)
    async def lead_not_found_handler(request: Request, exc: LeadNotFoundError):
        return JSONResponse(
            status_code=404,
            content={"detail": str(exc), "lead_id": str(exc.lead_id)},
        )

    @app.exception_handler(ModelNotLoadedError)
    async def model_not_loaded_handler(request: Request, exc: ModelNotLoadedError):
        return JSONResponse(
            status_code=503,
            content={"detail": str(exc)},
        )

    @app.exception_handler(FeatureComputationError)
    async def feature_error_handler(request: Request, exc: FeatureComputationError):
        request_id = getattr(request.state, "request_id", "unknown")
        return JSONResponse(
            status_code=500,
            content={"detail": exc.detail, "request_id": request_id},
        )

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception):
        request_id = getattr(request.state, "request_id", "unknown")
        logger.error("unhandled_exception", request_id=request_id, error=str(exc), exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "request_id": request_id},
        )

    return app


app = create_app()
