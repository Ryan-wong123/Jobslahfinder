#!/usr/bin/env sh
set -eu

: "${POSTGRES_DB:?POSTGRES_DB is required}"
: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${BACKUP_DIR:=/var/backups/jobapp}"
: "${UPLOAD_DIR:=/var/lib/jobapp/uploads}"
: "${LOG_DIR:=/var/log/jobapp}"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
destination="${BACKUP_DIR}/${timestamp}"

mkdir -p "$destination"
chmod 700 "$BACKUP_DIR" "$destination"

pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f "$destination/postgres.dump"

if [ -d "$UPLOAD_DIR" ]; then
  tar -C "$UPLOAD_DIR" -czf "$destination/resume-storage.tar.gz" .
fi

if [ -d "$LOG_DIR" ]; then
  tar -C "$LOG_DIR" -czf "$destination/app-logs.tar.gz" .
fi

chmod 600 "$destination"/*
find "$BACKUP_DIR" -mindepth 1 -maxdepth 1 -type d -mtime +14 -exec rm -rf {} \;

printf '%s\n' "Backup written to $destination"
