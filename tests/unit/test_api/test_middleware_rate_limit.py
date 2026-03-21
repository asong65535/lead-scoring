"""Tests for rate limiting middleware."""

from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from src.api.middleware.rate_limit import RateLimitMiddleware


async def homepage(request):
    return PlainTextResponse("ok")


def test_allows_requests_under_limit():
    app = Starlette(routes=[Route("/", homepage)])
    app = RateLimitMiddleware(app, max_requests=5, window_seconds=60)
    client = TestClient(app)
    for _ in range(5):
        resp = client.get("/")
        assert resp.status_code == 200


def test_blocks_requests_over_limit():
    app = Starlette(routes=[Route("/", homepage)])
    app = RateLimitMiddleware(app, max_requests=3, window_seconds=60)
    client = TestClient(app)
    for _ in range(3):
        client.get("/")
    resp = client.get("/")
    assert resp.status_code == 429
    assert resp.json()["detail"] == "Rate limit exceeded"


def test_non_http_passes_through():
    """Non-http scopes (e.g. lifespan) pass through without rate limiting.

    TestClient sends lifespan events on startup. With max_requests=1,
    if lifespan counted against the limit the first real HTTP request
    would be blocked.
    """
    app = Starlette(routes=[Route("/", homepage)])
    app = RateLimitMiddleware(app, max_requests=1, window_seconds=60)
    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
