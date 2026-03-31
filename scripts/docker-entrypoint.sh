#!/usr/bin/env bash
set -euo pipefail

# --- Wait for Postgres ---
echo "Waiting for Postgres at ${DB_HOST}:${DB_PORT}..."
timeout=30
elapsed=0
until pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -q 2>/dev/null; do
    elapsed=$((elapsed + 1))
    if [ "$elapsed" -ge "$timeout" ]; then
        echo "ERROR: Postgres not ready after ${timeout}s"
        exit 1
    fi
    sleep 1
done
echo "Postgres is ready."

# --- Run Alembic migrations ---
echo "Running database migrations..."
alembic upgrade head
echo "Migrations complete."

# --- Start Uvicorn ---
WORKERS="${UVICORN_WORKERS:-1}"
LOG_LEVEL="${UVICORN_LOG_LEVEL:-info}"

echo "Starting Uvicorn (workers=${WORKERS}, log_level=${LOG_LEVEL})..."
exec uvicorn src.api.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers "$WORKERS" \
    --log-level "$LOG_LEVEL" \
    "$@"
