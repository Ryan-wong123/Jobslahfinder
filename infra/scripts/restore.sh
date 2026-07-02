#!/usr/bin/env sh
set -eu

: "${POSTGRES_DB:?POSTGRES_DB is required}"
: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${BACKUP_PATH:?BACKUP_PATH must point to a backup directory}"
: "${UPLOAD_DIR:=/var/lib/jobapp/uploads}"

if [ ! -f "$BACKUP_PATH/postgres.dump" ]; then
  printf '%s\n' "Missing $BACKUP_PATH/postgres.dump" >&2
  exit 1
fi

pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists "$BACKUP_PATH/postgres.dump"

if [ -f "$BACKUP_PATH/resume-storage.tar.gz" ]; then
  mkdir -p "$UPLOAD_DIR"
  chmod 700 "$UPLOAD_DIR"
  tar -C "$UPLOAD_DIR" -xzf "$BACKUP_PATH/resume-storage.tar.gz"
fi

printf '%s\n' "Restore completed from $BACKUP_PATH"
