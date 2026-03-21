"""In-memory sliding-window rate limiter per client IP."""

import time
from collections import defaultdict

import structlog
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

logger = structlog.get_logger()


class RateLimitMiddleware:
    def __init__(self, app: ASGIApp, max_requests: int = 100, window_seconds: int = 60):
        self.app = app
        self._max_requests = max_requests
        self._window = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)

    def _get_client_ip(self, scope: Scope) -> str:
        client = scope.get("client")
        if client:
            return client[0]
        return "unknown"

    def _is_rate_limited(self, ip: str) -> bool:
        now = time.monotonic()
        timestamps = self._requests[ip]

        # Prune expired entries
        cutoff = now - self._window
        self._requests[ip] = [t for t in timestamps if t > cutoff]

        if len(self._requests[ip]) >= self._max_requests:
            return True

        self._requests[ip].append(now)
        return False

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        ip = self._get_client_ip(scope)
        if self._is_rate_limited(ip):
            logger.warning("rate_limited", ip=ip, path=scope.get("path"))
            response = JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
