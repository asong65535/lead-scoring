---
title: Deployment
description: Docker containers, Compose services, Nginx reverse proxy, and local development.
---

## Container Architecture

### App Image

Built from a multi-stage `Dockerfile` based on `python:3.13-slim`.

**Builder stage** installs Poetry 2.3.2 into an isolated venv, then exports production
dependencies to `requirements.txt` (no dev dependencies, no hashes) using
`poetry-plugin-export`.

**Runtime stage** starts from a fresh `python:3.13-slim` layer and:

- Creates a non-root user (`appuser`, UID 1000, group `appgroup`, GID 1000).
- Installs `curl` for health checks.
- Copies `requirements.txt` from the builder and installs with `pip --no-cache-dir`.
- Copies application code owned by `appuser:appgroup`.
- Creates `models/`, `data/`, and `logs/` directories owned by `appuser`.
- Switches to `appuser` for the process runtime.
- Exposes port **8000**.

The image health check calls `curl -f http://localhost:8000/health` every 30 s
(timeout 10 s, 3 retries, 5 s start period).

Default entrypoint:

```
uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

### Database Image

`postgres:15-alpine`. Health check: `pg_isready -U postgres -d lead_scoring`
(interval 10 s, timeout 5 s, 5 retries).

### Redis (Planned)

Redis is commented out in `compose.yaml`. When caching is needed, uncomment the
`redis` service block (`redis:7-alpine`, port **6379**). The `redis_data` named
volume definition is also commented out and must be re-enabled at the same time.

### Current State

PostgreSQL is fully containerized. The FastAPI app can run either containerized
(via `docker compose`) or directly on the host. The ML model is loaded from disk
at startup; it is not served as a separate service.

---

## Local Development

### docker compose walkthrough

**`nginx` service**

| Setting | Value |
|---|---|
| Image | `nginx:alpine` |
| Container name | `lead-scoring-nginx` |
| Port | `80:80` |
| Depends on | `app` (condition: `service_healthy`) |
| Restart policy | `unless-stopped` |
| Network | `lead-scoring-network` |

Configuration file mounted from `config/nginx.conf`.

**`app` service**

| Setting | Value |
|---|---|
| Container name | `lead-scoring-app` |
| Port | `expose: 8000 (internal only)` |
| Depends on | `postgres` (condition: `service_healthy`) |
| Restart policy | `unless-stopped` |
| Network | `lead-scoring-network` |

Command override: `["--reload"]` (passed to `docker-entrypoint.sh`).

Environment variables set by compose (these are overridden by `.env` if present):

| Variable | Value |
|---|---|
| `ENVIRONMENT` | `development` |
| `DEBUG` | `true` |
| `DB_HOST` | `postgres` |
| `DB_PORT` | `5432` |
| `DB_USER` | `postgres` |
| `DB_PASSWORD` | `postgres` |
| `DB_NAME` | `lead_scoring` |

Volumes mounted into `/app/`:

| Host path | Container path | Mode |
|---|---|---|
| `./src` | `/app/src` | read-only |
| `./config` | `/app/config` | read-only |
| `./alembic` | `/app/alembic` | read-only |
| `./alembic.ini` | `/app/alembic.ini` | read-only |
| `./models` | `/app/models` | read-write |
| `./data` | `/app/data` | read-write |

Source and config are mounted read-only so `--reload` picks up changes without
rebuilding the image. `models/` and `data/` are writable so the app can persist
artifacts at runtime.

**`postgres` service**

| Setting | Value |
|---|---|
| Image | `postgres:15-alpine` |
| Container name | `lead-scoring-db` |
| Port | `5432:5432` |
| Volume | `postgres_data:/var/lib/postgresql/data` |
| Network | `lead-scoring-network` |

The app connects to the database using hostname `postgres` (the service name).

**`scripts` service**

| Setting | Value |
|---|---|
| Profile | `scripts` (only runs when explicitly invoked) |
| User | `root` (for bind-mount write access) |
| Depends on | `postgres` (condition: `service_healthy`) |
| Entrypoint | `[]` (overrides docker-entrypoint.sh) |

Used for one-off tasks: migrations, seeding, training, backups. Invoked via `docker compose run --rm scripts <command>` or the Makefile targets.

**Network**

A single bridge network named `lead-scoring-network` isolates the services.

**Named volumes**

`postgres_data` persists database files across container restarts.

### Common commands

```bash
# Start all services in the background
docker compose up -d

# Stop and remove containers (data volume is preserved)
docker compose down

# Tail application logs
docker compose logs -f app

# Rebuild the app image after dependency changes
docker compose build app

# Run a one-off migration (while postgres is running)
docker compose run --rm app alembic upgrade head
```

For migration commands and schema details see [Database](database.md).

### Makefile targets

The `Makefile` wraps common Docker Compose workflows:

| Target | Command | Purpose |
|--------|---------|---------|
| `make bootstrap` | Build + seed + train + start | Full setup from scratch |
| `make up` | `docker compose up -d` | Start all services |
| `make down` | `docker compose down` | Stop all services |
| `make build` | `docker compose build` | Rebuild images |
| `make logs` | `docker compose logs -f` | Tail logs |
| `make seed` | Run `seed_db.py` in scripts container | Load CSV data |
| `make events` | Run `generate_events.py` in scripts container | Generate synthetic events |
| `make train` | Run `train.py --set-active` in scripts container | Train and activate model |
| `make retrain` | Run `retrain.py` in scripts container | Retrain with comparison gates |
| `make score` | Run `batch_score.py` in scripts container | Batch score all leads |
| `make backup` | Run `backup_db.sh` in scripts container | pg_dump with gzip |
| `make clean` | `docker compose down -v` | Stop and delete volumes |

---

## Production Architecture

### Nginx Reverse Proxy

Nginx (`nginx:alpine`) sits in front of the FastAPI app and handles:

- Reverse proxy to Uvicorn on port 8000 (internal only; `app` uses `expose`, not `ports`)
- Security headers (X-Frame-Options, X-Content-Type-Options, Referrer-Policy)
- Gzip compression for JSON responses
- 1 MB request body limit (`client_max_body_size`)
- Structured access logging

Configuration: `config/nginx.conf`, mounted read-only into the container.

The API is accessible at **http://localhost:80**. The app container does not expose port 8000 to the host.

### Resource Limits

| Service | Memory | CPUs |
|---------|--------|------|
| `nginx` | 128 MB | 0.25 |
| `app` | 2 GB | 2.0 |
| `postgres` | 512 MB | 0.5 |

### Secrets

All secrets are read from `.env` at the project root (listed in `.gitignore`). Copy `.env.example` as a starting point. Key secrets:

- `DB_USER`, `DB_PASSWORD` — database credentials
- `CRM_HUBSPOT_ACCESS_TOKEN` — HubSpot API token (if CRM enabled)
- `CRM_WEBHOOK_CLIENT_SECRET` — HubSpot webhook HMAC secret

Never bake secrets into Docker images or commit `.env` to git.

### Restart Policies

All services use `restart: unless-stopped`. Docker Compose starts them automatically on host reboot (assuming the Docker daemon is enabled via systemd).

### Health Probes

| Probe | Path | Used by |
|-------|------|---------|
| `/health/live` | Liveness (process alive) | Docker healthcheck |
| `/health/ready` | Readiness (DB + model) | Manual / load balancer |
| `/health` | Full status | Monitoring |

---

## Model Serving

**Current behaviour**: At startup the lifespan handler reads the active model
version from the `model_registry` table and loads the artifact from disk into
memory. The default path is `models/current.joblib` (env var
`MODEL_ARTIFACT_PATH`).

**Hot reload**: Sending `POST /admin/reload-model` swaps the in-memory model
without restarting the process. Useful after training a new version and
promoting it in the registry. The reload is protected by an `asyncio.Lock`
to prevent concurrent reloads from corrupting model state. After loading, the
model is validated for correct Pipeline structure (`predict_proba` method and
`named_steps` containing a `"classifier"` step).

**Graceful degradation**: If the model fails to load at startup (missing artifact,
corrupted file, wrong format), the app starts anyway with `model = None`. Scoring
endpoints return 503 until a model is successfully loaded via the reload endpoint.

**Future**: Model artifacts will either be baked into the image at build time
or fetched from object storage (e.g., S3) on startup, removing the dependency
on a host-mounted `models/` directory.

For `MODEL_ARTIFACT_PATH` and related env vars see [Configuration](configuration.md).

---

## Authentication & API Keys

The API requires Bearer token authentication by default (`AUTH_ENABLED=true`).

### Key Management CLI

Use `scripts/manage_keys.py` to create, revoke, and list API keys:

```bash
# Create a new key (prints the raw key once — save it)
poetry run python scripts/manage_keys.py create --label "production"

# List all keys with status
poetry run python scripts/manage_keys.py list

# Revoke a key
poetry run python scripts/manage_keys.py revoke --key <raw-key>
```

Keys are stored as SHA-256 hashes in the `api_keys` table — raw keys cannot
be recovered from the database. See [Database](database.md) for the table schema.

### Using API keys

Pass the raw key as a Bearer token:

```bash
curl -H "Authorization: Bearer <api-key>" http://localhost:8000/score/<lead-id> -X POST
```

Health probes (`/health/live`, `/health/ready`) and OpenAPI docs (`/docs`, `/redoc`,
`/openapi.json`) are exempt from authentication by default. Exempt paths are
configurable via `AUTH_EXEMPT_PATHS`.

### Disabling authentication

Set `AUTH_ENABLED=false` in the environment to disable auth entirely (e.g., for
local development or integration testing).

---

## Retraining Pipeline

### Running a retrain

```bash
# Weekly retrain (cron calls this)
docker compose run --rm app python scripts/retrain.py

# With hyperparameter tuning
docker compose run --rm app python scripts/retrain.py --tune

# Force promote regardless of metric comparison
docker compose run --rm app python scripts/retrain.py --force

# Dry run — train and compare but don't persist or promote
docker compose run --rm app python scripts/retrain.py --dry-run
```

### Example crontab

```cron
# Retrain every Sunday at 2am
0 2 * * 0 cd /path/to/lead-scoring && docker compose run --rm app python scripts/retrain.py >> logs/retrain.log 2>&1
```

### How promotion works

1. New model is trained and evaluated on the holdout set
2. Metrics are compared against the active model:
   - AUC-ROC must not drop more than 5% relative
   - Calibration error must not increase more than 0.05 absolute
3. If both gates pass: model is registered as active, API is hot-reloaded
4. If either gate fails: model is registered but inactive, webhook alert sent
5. Every run is recorded in the `retraining_runs` table

### Webhook alerts

Set `RETRAIN_WEBHOOK_URL` to receive JSON alerts. Events: `retrain.success`, `retrain.blocked`, `retrain.failed`, `drift.detected`.
