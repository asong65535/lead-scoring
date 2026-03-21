# API Reference

## Overview

The Lead Scoring API is a FastAPI application created via `create_app()` in `src/api/main.py`.

### Startup (lifespan)

On startup, the lifespan context manager:

1. Calls `configure_logging(debug=settings.debug)` to initialise structlog.
2. Queries the `model_registry` table for the row where `is_active = true`.
3. If found and the artifact file exists, loads the model via `load_model()` and stores it in `app.state.model` / `app.state.model_version`.
4. If no active model exists or the artifact is missing, sets both to `None` and logs a warning. Scoring endpoints will return 503 until a model is loaded.
5. On shutdown, disposes the async database engine.

### Running the server

```
uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

Default port: **8000**.

### OpenAPI docs

Interactive docs are available only when `DEBUG=true`:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

In production (`DEBUG=false`) both URLs return 404.

### CORS

| Mode | Allowed origins |
|------|----------------|
| `DEBUG=true` | `*` (all origins) |
| `DEBUG=false` | None |

See [configuration.md](configuration.md) for all environment variable details.

---

## Endpoints

### Summary

| Method | Path | Purpose | Status |
|--------|------|---------|--------|
| GET | `/health` | Full health check with DB and model status | Stable |
| GET | `/health/live` | Liveness probe (process alive check) | Stable |
| GET | `/health/ready` | Readiness probe (DB + model ready) | Stable |
| POST | `/score/{lead_id}` | Score a single lead | Stable |
| POST | `/score/batch` | Score up to 500 leads in one request | Stable |
| GET | `/admin/model` | Return active model metadata | Stable |
| POST | `/admin/reload-model` | Hot-reload model from registry into app state | Stable |
| POST | `/webhooks/hubspot` | HubSpot webhook stub | Stub (Phase 7) |
| POST | `/webhooks/salesforce` | Salesforce webhook stub | Stub (Phase 7) |

---

### GET /health

Full health check. Checks database connectivity and whether a model is loaded. Used by Docker health checks and load balancers.

**Response 200**

```json
{
  "status": "healthy",
  "timestamp": "2026-03-21T12:00:00.000000+00:00",
  "version": "0.1.0",
  "environment": "production",
  "checks": {
    "database": { "healthy": true },
    "model_loaded": { "healthy": true, "loaded": true, "version": "v1.0.0" }
  }
}
```

`status` is `"healthy"` when all checks pass, `"degraded"` otherwise. When the model is not loaded, `model_loaded` returns `{"healthy": false, "loaded": false, "message": "No model loaded"}`.

---

### GET /health/live

Kubernetes liveness probe. Returns 200 immediately if the process is running. No dependency checks.

**Response 200**

```json
{ "status": "alive" }
```

> This path is excluded from access logging to reduce noise.

---

### GET /health/ready

Kubernetes readiness probe. Returns `ready: true` only when both the database and the model are available.

**Response 200**

```json
{
  "ready": true,
  "checks": {
    "database": true,
    "model": true
  }
}
```

When either dependency is unavailable, `ready` is `false` and the corresponding check is `false`.

---

### POST /score/{lead_id}

Score a single lead by its UUID. Fetches features from the database, runs inference, persists the prediction, and returns the result.

**Path parameter:** `lead_id` — UUID of the lead.

**Response 200**

```json
{
  "lead_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "score": 0.87,
  "bucket": "A",
  "model_version": "v1.0.0",
  "top_factors": [
    { "feature": "total_time_spent", "impact": 0.32, "value": 1450 },
    { "feature": "page_views_per_visit", "impact": 0.21, "value": 4.5 },
    { "feature": "lead_source_olm", "impact": -0.08, "value": 1 }
  ],
  "scored_at": "2026-03-21T12:00:01.234567+00:00"
}
```

`score` is a probability in `[0.0, 1.0]`. `bucket` is one of `A`, `B`, `C`, `D` (thresholds configured via `BUCKET_A_THRESHOLD`, `BUCKET_B_THRESHOLD`, `BUCKET_C_THRESHOLD` settings).

**Error responses**

| Condition | Status | Body |
|-----------|--------|------|
| Lead UUID not in database | 404 | `{"detail": "Lead not found: <uuid>", "lead_id": "<uuid>"}` |
| No model loaded | 503 | `{"detail": "Model not available"}` |
| Feature computation failure | 500 | `{"detail": "<message>", "request_id": "<uuid>"}` |

---

### POST /score/batch

Score up to 500 leads in a single request. Leads that cannot be found are returned in the `errors` list; successfully scored leads appear in `results`.

**Request body**

```json
{
  "lead_ids": [
    "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "1b9d6bcd-bbfd-4b2d-9b5d-ab8dfbbd4bed"
  ]
}
```

`lead_ids` must contain between 1 and 500 UUIDs.

**Response 200**

```json
{
  "results": [
    {
      "lead_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "score": 0.87,
      "bucket": "A",
      "model_version": "v1.0.0",
      "top_factors": [
        { "feature": "total_time_spent", "impact": 0.32, "value": 1450 }
      ],
      "scored_at": "2026-03-21T12:00:01.234567+00:00"
    }
  ],
  "errors": [
    {
      "lead_id": "1b9d6bcd-bbfd-4b2d-9b5d-ab8dfbbd4bed",
      "error": "Lead not found"
    }
  ]
}
```

A 200 is returned even when some leads fail; inspect `errors` to identify partial failures.

---

### GET /admin/model

Return metadata for the currently active model from the `model_registry` table.

**Response 200**

```json
{
  "version": "v1.0.0",
  "metrics": {
    "roc_auc": 0.91,
    "f1": 0.78,
    "precision": 0.82,
    "recall": 0.74
  },
  "feature_columns": [
    "total_time_spent",
    "page_views_per_visit",
    "lead_source_olm"
  ],
  "trained_at": "2026-03-20T09:15:00.000000+00:00",
  "is_active": true
}
```

**Error responses**

| Condition | Status | Body |
|-----------|--------|------|
| No active model in registry | 404 | `{"detail": "No active model found"}` |

---

### POST /admin/reload-model

Hot-reload the active model from disk into `app.state` without restarting the server. Useful after promoting a new model version in the registry.

**No request body required.**

**Response 200**

```json
{
  "version": "v1.1.0",
  "message": "Model v1.1.0 loaded successfully"
}
```

**Error responses**

| Condition | Status | Body |
|-----------|--------|------|
| No active model in registry | 500 | `{"detail": "No active model in registry"}` |
| Artifact file missing on disk | 500 | `{"detail": "Model artifact not found: <path>"}` |

---

### POST /webhooks/hubspot

Stub endpoint for HubSpot webhook delivery. Accepts any JSON payload, logs the payload size, and returns `{"status": "received"}`. CRM event processing (contact sync, rescoring) is deferred to Phase 7.

**Response 200**

```json
{ "status": "received" }
```

---

### POST /webhooks/salesforce

Stub endpoint for Salesforce webhook delivery. Same behaviour as `/webhooks/hubspot`. CRM logic deferred to Phase 7.

**Response 200**

```json
{ "status": "received" }
```

---

## Dependency Injection

Dependencies are defined in `src/api/dependencies.py` across three scopes.

### `get_model(request)` — application scope

Returns `(model: Pipeline, model_version: str)` from `app.state`. Raises `ModelNotLoadedError` (→ 503) if `app.state.model` is `None`. Because the model is loaded once at startup and stored on app state, this dependency does not create any database or IO overhead per request.

### `get_feature_computer()` — engine scope

Returns a `FeatureComputer` instance constructed with `async_engine`. The computer manages its own async sessions internally for feature reads. A new instance is created per call, but the underlying engine is shared at the process level.

### `get_scoring_service(request, session)` — per-request scope

Composes the above into a `ScoringService`:

```
get_model(request)         → model, version
get_feature_computer()     → feature_computer
get_settings()             → bucket thresholds
Depends(get_session)       → async DB session (for prediction writes)
```

The `ScoringService` is instantiated fresh for each request, ensuring the DB session is properly scoped and cleaned up.

---

## Middleware

Both middlewares use the raw ASGI interface (`__call__(scope, receive, send)`) rather than Starlette's `BaseHTTPMiddleware`. This avoids double-reading the request body, gives full control over response header injection, and improves performance on streaming responses.

Middleware is applied in the following order (outermost to innermost as registered in `create_app()`):

1. `LoggingMiddleware` — outermost, captures total request duration
2. `RequestIDMiddleware` — injects request ID before logging reads it
3. `CORSMiddleware` — Starlette built-in, innermost

### RequestIDMiddleware (`src/api/middleware/request_id.py`)

For every `http` or `websocket` scope:

1. Reads the `X-Request-ID` request header.
2. Uses the header value if present; otherwise generates a `uuid4` string.
3. Stores the ID in `scope["state"]["request_id"]` (accessible downstream as `request.state.request_id`).
4. Appends `X-Request-ID: <id>` to all response headers.

### LoggingMiddleware (`src/api/middleware/logging.py`)

For every `http` scope, unless the path is `/health/live`:

1. Records `time.monotonic()` before delegating to the next layer.
2. Captures `status_code` by intercepting the `http.response.start` ASGI message.
3. After the response completes (in a `finally` block), emits a structlog `http_request` event:

   ```json
   {
     "event": "http_request",
     "method": "POST",
     "path": "/score/abc123",
     "status_code": 200,
     "duration_ms": 42.7,
     "request_id": "550e8400-e29b-41d4-a716-446655440000"
   }
   ```

**Log format** is controlled by `configure_logging(debug)` called at startup:

| Mode | Renderer |
|------|----------|
| `DEBUG=true` | `structlog.dev.ConsoleRenderer` (human-readable, coloured) |
| `DEBUG=false` | `structlog.processors.JSONRenderer` (one JSON object per line) |

---

## Error Handling

Custom exceptions are defined in `src/api/exceptions.py`. Handlers are registered in `create_app()`.

| Exception | HTTP status | Response body |
|-----------|-------------|---------------|
| `LeadNotFoundError(lead_id)` | 404 | `{"detail": "Lead not found: <uuid>", "lead_id": "<uuid>"}` |
| `ModelNotLoadedError()` | 503 | `{"detail": "Model not available"}` |
| `FeatureComputationError(detail)` | 500 | `{"detail": "<message>", "request_id": "<uuid>"}` |
| Any unhandled `Exception` | 500 | `{"detail": "Internal server error", "request_id": "<uuid>"}` |

`request_id` in 500 responses is read from `request.state.request_id` (set by `RequestIDMiddleware`). If the middleware has not run (e.g., very early startup failure), it falls back to `"unknown"`.

---

## OpenAPI

Interactive documentation is enabled only when `DEBUG=true`:

| Interface | URL |
|-----------|-----|
| Swagger UI | `http://localhost:8000/docs` |
| ReDoc | `http://localhost:8000/redoc` |

Both URLs return 404 in production. The OpenAPI schema can also be fetched programmatically at `/openapi.json` (controlled by FastAPI separately from the UI toggle).
