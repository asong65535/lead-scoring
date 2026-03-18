"""
Health check endpoints.

Provides endpoints for monitoring application health and readiness.
"""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel


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
    # TODO: Implement actual database check in Phase 2
    # For now, return a placeholder
    return {
        "healthy": True,
        "message": "Database check not yet implemented",
    }


async def _check_database_connection() -> bool:
    """Check if database is connected (simple bool for readiness)."""
    # TODO: Implement in Phase 2
    return True


def _check_model(request: Request) -> dict[str, Any]:
    """Check if ML model is loaded and return details."""
    model = getattr(request.app.state, "model", None)
    
    if model is None:
        return {
            "healthy": True,  # Model not being loaded yet is okay
            "loaded": False,
            "message": "Model not yet loaded (Phase 5)",
        }
    
    return {
        "healthy": True,
        "loaded": True,
        "version": getattr(request.app.state, "model_version", "unknown"),
    }


def _check_model_loaded(request: Request) -> bool:
    """Check if model is loaded (simple bool for readiness)."""
    # For now, return True since model loading is Phase 5
    # Later, this should return False if model failed to load
    return True
