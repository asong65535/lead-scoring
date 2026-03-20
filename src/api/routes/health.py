"""
Health check endpoints.

Provides endpoints for monitoring application health and readiness.
"""

from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel
from sqlalchemy import text

from src.models.database import async_engine

logger = structlog.get_logger()


router = APIRouter()


class HealthResponse(BaseModel):
    """Health check response model."""
    
    status: str
    timestamp: str
    version: str
    environment: str
    checks: dict[str, Any]


class ReadinessResponse(BaseModel):
    """Readiness check response model."""
    
    ready: bool
    checks: dict[str, bool]


@router.get("/health", response_model=HealthResponse)
async def health_check(request: Request) -> HealthResponse:
    """
    Basic health check endpoint.
    
    Returns application status and version information.
    Used by Docker health checks and load balancers.
    """
    settings = request.app.state.settings
    
    # Perform health checks
    checks = {
        "database": await _check_database(),
        "model_loaded": _check_model(request),
    }
    
    # Determine overall status
    all_healthy = all(
        check.get("healthy", False) if isinstance(check, dict) else check
        for check in checks.values()
    )
    
    return HealthResponse(
        status="healthy" if all_healthy else "degraded",
        timestamp=datetime.now(timezone.utc).isoformat(),
        version=settings.app_version,
        environment=settings.environment,
        checks=checks,
    )


@router.get("/health/live")
async def liveness_check() -> dict[str, str]:
    """
    Kubernetes liveness probe endpoint.
    
    Simple check that the application is running.
    Returns 200 if the process is alive.
    """
    return {"status": "alive"}


@router.get("/health/ready", response_model=ReadinessResponse)
async def readiness_check(request: Request) -> ReadinessResponse:
    """
    Kubernetes readiness probe endpoint.
    
    Checks if the application is ready to receive traffic.
    Returns ready=true only if all dependencies are available.
    """
    checks = {
        "database": await _check_database_connection(),
        "model": _check_model_loaded(request),
    }
    
    return ReadinessResponse(
        ready=all(checks.values()),
        checks=checks,
    )


async def _check_database() -> dict[str, Any]:
    """Check database connectivity and return details."""
    try:
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"healthy": True}
    except Exception as exc:
        logger.error("database_health_check_failed", error=str(exc))
        return {"healthy": False, "error": str(exc)}


async def _check_database_connection() -> bool:
    """Check if database is connected (simple bool for readiness)."""
    try:
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def _check_model(request: Request) -> dict[str, Any]:
    """Check if ML model is loaded and return details."""
    model = getattr(request.app.state, "model", None)
    
    if model is None:
        return {
            "healthy": False,
            "loaded": False,
            "message": "No model loaded",
        }
    
    return {
        "healthy": True,
        "loaded": True,
        "version": getattr(request.app.state, "model_version", "unknown"),
    }


def _check_model_loaded(request: Request) -> bool:
    """Check if model is loaded (simple bool for readiness)."""
    return getattr(request.app.state, "model", None) is not None
