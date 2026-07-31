#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
STAMP="$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

: "${PGHOST:=db}" "${PGPORT:=5432}" "${PGDATABASE:=shahrdari_ai}" "${PGUSER:=postgres}"
pg_dump --format=custom --file="$BACKUP_DIR/db_${STAMP}.dump" "$PGDATABASE"
if [[ -d "${STORAGE_PATH:-/app/storage}" ]]; then
  tar -czf "$BACKUP_DIR/storage_${STAMP}.tar.gz" -C "${STORAGE_PATH:-/app/storage}" .
fi
find "$BACKUP_DIR" -type f -mtime "+$RETENTION_DAYS" -delete
printf 'Backup completed: %s\n' "$STAMP"
