#!/usr/bin/env bash
set -euo pipefail

# Load defaults from environment (set by compose env_file)
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_USER="${DB_USER:-postgres}"
DB_NAME="${DB_NAME:-lead_scoring}"
export PGPASSWORD="${DB_PASSWORD:-postgres}"

BACKUP_DIR="${BACKUP_DIR:-/app/backups}"
mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
FILENAME="${BACKUP_DIR}/${DB_NAME}_${TIMESTAMP}.sql.gz"

echo "Backing up ${DB_NAME} to ${FILENAME}..."
pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" "$DB_NAME" | gzip > "$FILENAME"

echo "Backup complete: ${FILENAME} ($(du -h "$FILENAME" | cut -f1))"

# Prune backups older than 7 days
find "$BACKUP_DIR" -name "*.sql.gz" -mtime +7 -delete 2>/dev/null || true
echo "Pruned backups older than 7 days."
