"""
Lead Scoring API - Main Application

FastAPI application factory with lifespan management.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config.settings import get_settings
from src.api.routes import health


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan manager.
    
    Handles startup and shutdown tasks:
    - Startup: Load ML model, establish DB connection pool
    - Shutdown: Close connections, cleanup resources
    """
    settings = get_settings()
    
    # === Startup ===
    print(f"Starting {settings.app_name} v{settings.app_version}")
    print(f"Environment: {settings.environment}")
    print(f"Debug mode: {settings.debug}")
    
    # TODO: Initialize database connection pool
    # TODO: Load ML model into memory
    
    # Store shared resources in app.state
    app.state.settings = settings
    app.state.model = None  # Will be loaded in Phase 5
    
    yield
    
    # === Shutdown ===
    print("Shutting down application...")
    # TODO: Close database connections
    # TODO: Cleanup resources


def create_app() -> FastAPI:
    """
    Application factory.
    
    Creates and configures the FastAPI application.
    """
    settings = get_settings()
    
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="ML-powered lead scoring system with CRM integration",
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        lifespan=lifespan,
    )
    
    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.debug else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Register routes
    app.include_router(health.router, tags=["Health"])
    
    # Future routers (to be added in later phases):
    # app.include_router(scoring.router, prefix="/score", tags=["Scoring"])
    # app.include_router(webhooks.router, prefix="/webhooks", tags=["Webhooks"])
    # app.include_router(contacts.router, prefix="/contacts", tags=["Contacts"])
    # app.include_router(admin.router, prefix="/admin", tags=["Admin"])
    
    return app


# Create the app instance
app = create_app()
