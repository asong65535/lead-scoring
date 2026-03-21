"""ASGI middleware for API key authentication via Bearer token."""

import hashlib

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, AsyncEngine
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from src.models.api_key import APIKey

logger = structlog.get_logger()


class AuthMiddleware:
    def __init__(self, app: ASGIApp, engine: AsyncEngine, exempt_paths: list[str] | None = None):
        self.app = app
        self._session_factory = async_sessionmaker(
            bind=engine, class_=AsyncSession, expire_on_commit=False,
        )
        self._exempt_paths = set(exempt_paths or [])

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http",):
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path in self._exempt_paths:
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        auth_header = headers.get(b"authorization", b"").decode()

        if not auth_header.startswith("Bearer "):
            response = JSONResponse(
                status_code=401,
                content={"detail": "Missing or invalid Authorization header"},
            )
            await response(scope, receive, send)
            return

        token = auth_header[7:]
        key_hash = hashlib.sha256(token.encode()).hexdigest()

        async with self._session_factory() as session:
            result = await session.execute(
                select(APIKey.id).where(
                    APIKey.key_hash == key_hash,
                    APIKey.is_active == True,  # noqa: E712
                )
            )
            api_key = result.scalar_one_or_none()

        if api_key is None:
            logger.warning("auth_failed", path=path)
            response = JSONResponse(
                status_code=401,
                content={"detail": "Invalid API key"},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
