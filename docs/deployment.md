# Deployment

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

**`app` service**

| Setting | Value |
|---|---|
| Container name | `lead-scoring-app` |
| Port | `8000:8000` |
| Depends on | `postgres` (condition: `service_healthy`) |
| Restart policy | `unless-stopped` |
| Network | `lead-scoring-network` |

Command override for hot reload:

```
uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload
```

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

---

## Production (Planned)

The following describes the intended production architecture. It is **not yet
implemented**.

**Database**: Managed PostgreSQL (e.g., AWS RDS, Cloud SQL) replaces the
containerized instance. The `DB_HOST`, `DB_USER`, `DB_PASSWORD`, and `DB_NAME`
env vars point at the managed endpoint.

**Application**: Deployed as a Kubernetes `Deployment`. Resource requests and
limits are set per-pod; the app is stateless so horizontal scaling is
straightforward.

**Health probes**:

| Probe | Path |
|---|---|
| Liveness | `/health/live` |
| Readiness | `/health/ready` |

**Secrets**: `DB_PASSWORD` and API keys are stored in Kubernetes `Secret`
objects or an external secret manager (e.g., AWS Secrets Manager, Vault).
They are injected as environment variables; never baked into the image.

**Scaling**: Because the app holds no session state, the replica count can be
adjusted freely. DB connection pooling (`DB_POOL_SIZE`, `DB_MAX_OVERFLOW`)
prevents connection exhaustion under load.

**Ingress**: Nginx ingress controller or a cloud load balancer handles TLS
termination. The app itself listens on plain HTTP internally.

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
