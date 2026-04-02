---
title: Operational Runbook
description: Health checks, troubleshooting, rollback procedures, and backup/restore.
---

Day-to-day operations guide for the lead scoring system.

For architecture details see [Architecture](architecture.md). For configuration reference see [Configuration](configuration.md).

---

## Health Checks

### Quick status check

```bash
curl http://localhost/health
```

Returns `"healthy"` when both the database and model are available, `"degraded"` otherwise. Includes model version and per-check details.

### Kubernetes-style probes

| Probe | URL | What it checks |
|-------|-----|----------------|
| Liveness | `http://localhost/health/live` | Process is running |
| Readiness | `http://localhost/health/ready` | DB connected + model loaded |

### Docker health

```bash
docker compose ps
```

All services should show `(healthy)`. If `app` is `(health: starting)` for more than 30 seconds, check logs.

---

## Logs

### Application logs

```bash
# Tail all services
make logs

# App only
docker compose logs -f app

# Last 100 lines
docker compose logs --tail 100 app
```

Log format depends on `DEBUG`:
- `DEBUG=true` — human-readable colored output (development)
- `DEBUG=false` — JSON lines, one object per request (production)

Every request log includes `method`, `path`, `status_code`, `duration_ms`, and `request_id`.

### Nginx access logs

```bash
docker compose logs -f nginx
```

Structured JSON format with request method, URI, status, body bytes, upstream response time, and client IP.

### Finding a specific request

Use the `X-Request-ID` header (returned in every response) to trace a request through the logs:

```bash
docker compose logs app | grep "request_id.*<uuid>"
```

---

## Common Failure Modes

### Model not loaded (503 on scoring endpoints)

**Symptom:** `POST /score/{id}` returns `{"detail": "Model not available"}` with HTTP 503.

**Cause:** No model artifact on disk, or no active model in `model_registry`.

**Fix:**

```bash
# Check if a model is registered as active
docker compose exec postgres psql -U postgres -d lead_scoring \
  -c "SELECT version, artifact_path, is_active FROM model_registry ORDER BY trained_at DESC LIMIT 5"

# If no active model, train one
make train

# If model exists but wasn't loaded at startup, hot-reload
curl -X POST http://localhost/admin/reload-model \
  -H "Authorization: Bearer <api-key>"
```

### Database connection failures

**Symptom:** Health check returns `"database": {"healthy": false}`. Scoring returns 500.

**Fix:**

```bash
# Check postgres is running
docker compose ps postgres

# Check connectivity from app container
docker compose exec app curl -sf http://localhost:8000/health | python -m json.tool

# Restart postgres (data is persisted in volume)
docker compose restart postgres

# If pool exhaustion, check active connections
docker compose exec postgres psql -U postgres -d lead_scoring \
  -c "SELECT count(*) FROM pg_stat_activity WHERE datname='lead_scoring'"
```

### Rate limited (429)

**Symptom:** API returns `429 Too Many Requests`.

**Cause:** More than `RATE_LIMIT_REQUESTS` (default 100) requests from the same IP within `RATE_LIMIT_WINDOW_SECONDS` (default 60s).

**Fix:** Wait for the window to reset, or adjust limits in `.env`:

```
RATE_LIMIT_REQUESTS=500
RATE_LIMIT_WINDOW_SECONDS=60
```

Then restart the app: `docker compose restart app`.

### CRM writeback failures

**Symptom:** Scores return successfully but CRM is not updated. `crm_sync_log` rows show `status='failed'`.

**Diagnose:**

```bash
docker compose exec postgres psql -U postgres -d lead_scoring \
  -c "SELECT status, error_message, created_at FROM crm_sync_log ORDER BY created_at DESC LIMIT 10"
```

**Common causes:**
- Expired or invalid `CRM_HUBSPOT_ACCESS_TOKEN`
- HubSpot rate limit (check for `CRMRateLimitError` in error_message)
- Custom properties not created in HubSpot portal

**Retry failed writebacks:**

```bash
docker compose run --rm scripts python scripts/retry_writebacks.py
```

---

## Model Management

### View active model

```bash
curl http://localhost/admin/model \
  -H "Authorization: Bearer <api-key>"
```

Returns version, metrics (AUC-ROC, F1, precision, recall), feature columns, and training timestamp.

### Hot-reload model (no restart)

After training or promoting a new model version:

```bash
curl -X POST http://localhost/admin/reload-model \
  -H "Authorization: Bearer <api-key>"
```

The reload is atomic and protected by a lock. The API continues serving requests during the swap.

### Rollback to a previous model

```bash
# List all model versions
docker compose exec postgres psql -U postgres -d lead_scoring \
  -c "SELECT version, is_active, trained_at, metrics->>'auc_roc' as auc FROM model_registry ORDER BY trained_at DESC"

# Deactivate current model and activate a previous version
docker compose exec postgres psql -U postgres -d lead_scoring \
  -c "UPDATE model_registry SET is_active = false WHERE is_active = true;
      UPDATE model_registry SET is_active = true WHERE version = 'v1.X';"

# Hot-reload to pick up the change
curl -X POST http://localhost/admin/reload-model \
  -H "Authorization: Bearer <api-key>"
```

### Manual retraining

```bash
# Standard retrain (compares against active model, promotes if better)
make retrain

# With hyperparameter tuning
docker compose run --rm scripts python scripts/retrain.py --tune

# Force promote regardless of metric comparison
docker compose run --rm scripts python scripts/retrain.py --force

# Dry run — train and compare without persisting
docker compose run --rm scripts python scripts/retrain.py --dry-run
```

### Scheduled retraining (crontab)

```cron
# Retrain every Sunday at 2am
0 2 * * 0 cd /path/to/lead-scoring && docker compose run --rm scripts python scripts/retrain.py >> logs/retrain.log 2>&1
```

### Retraining audit trail

Every retrain attempt is logged in the `retraining_runs` table:

```bash
docker compose exec postgres psql -U postgres -d lead_scoring \
  -c "SELECT run_status, candidate_version, promoted, comparison_reason, duration_seconds
      FROM retraining_runs ORDER BY started_at DESC LIMIT 5"
```

---

## Backup & Restore

### Create a backup

```bash
make backup
```

Produces a gzipped pg_dump in `backups/` with timestamp. Backups older than 7 days are auto-pruned.

### Manual backup

```bash
docker compose exec postgres pg_dump -U postgres lead_scoring | gzip > backups/manual-$(date +%Y%m%d).sql.gz
```

### Restore from backup

```bash
# Stop the app to prevent writes during restore
docker compose stop app nginx

# Restore (drop and recreate)
gunzip -c backups/<filename>.sql.gz | docker compose exec -T postgres psql -U postgres -d lead_scoring

# Restart
docker compose up -d
```

> **Warning:** Restore overwrites the current database contents. Create a fresh backup before restoring.

---

## API Key Management

```bash
# Create a new key (save the printed key — it cannot be recovered)
docker compose run --rm scripts python scripts/manage_keys.py create --name "production"

# List all keys with status
docker compose run --rm scripts python scripts/manage_keys.py list

# Revoke a key
docker compose run --rm scripts python scripts/manage_keys.py revoke --key <raw-key>
```

Keys are stored as SHA-256 hashes. Revoked keys are immediately rejected by the auth middleware.

---

## Batch Scoring

```bash
# Score all leads
make score

# Score only recently updated leads
docker compose run --rm scripts python scripts/batch_score.py --since 2026-03-01

# Dry run (no persistence)
docker compose run --rm scripts python scripts/batch_score.py --dry-run

# Custom chunk size
docker compose run --rm scripts python scripts/batch_score.py --chunk-size 200
```

Output includes total scored, errors, bucket distribution, and elapsed time.

---

## Full Stack Restart

```bash
# Graceful restart (preserves data)
docker compose down && docker compose up -d

# Full rebuild (after code or dependency changes)
make build && docker compose up -d

# Nuclear option (destroys database volume)
make clean
make bootstrap
```

---

## Deployment Checklist

When deploying to a new machine:

1. Install Docker and Docker Compose
2. Clone the repository
3. `cp .env.example .env` and fill in real credentials
4. Place `data/Lead Scoring.csv` in the `data/` directory
5. `make bootstrap`
6. Create an API key: `docker compose run --rm scripts python scripts/manage_keys.py create --name prod`
7. Verify: `curl http://localhost/health`
8. (Optional) Set up crontab for weekly retraining and daily backups
