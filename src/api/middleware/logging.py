"""Structured logging middleware using structlog.

Logs every HTTP request with method, path, status_code, duration_ms,
and request_id. Excludes /health/live to reduce noise.

configure_logging() should be called once at application startup.
Uses raw ASGI protocol (not BaseHTTPMiddleware) to avoid streaming issues.
"""

import time

import structlog
from starlette.types import ASGIApp, Receive, Scope, Send

logger = structlog.get_logger()

EXCLUDED_PATHS = frozenset({"/health/live"})


def configure_logging(debug: bool = False) -> None:
    """Configure structlog — call once at startup."""
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if debug:
        processors.append(structlog.dev.ConsoleRenderer())
    else:
        processors.append(structlog.processors.JSONRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(0),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


class LoggingMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path in EXCLUDED_PATHS:
            await self.app(scope, receive, send)
            return

        start = time.monotonic()
        status_code = 500

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = round((time.monotonic() - start) * 1000, 2)
            request_id = scope.get("state", {}).get("request_id", "unknown")
            method = scope.get("method", "?")

            logger.info(
                "http_request",
                method=method,
                path=path,
                status_code=status_code,
                duration_ms=duration_ms,
                request_id=request_id,
            )
