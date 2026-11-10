#!/usr/bin/env bash
# Restore an encrypted, checksummed full-platform backup during maintenance.
# Usage: CONFIRM_RESTORE=restore-jobapp bash infra/scripts/restore-prod.sh <directory>
set -Eeuo pipefail
umask 077
cd "$(dirname "$0")/../.."
set -a; . ./.env; set +a
[ "${CONFIRM_RESTORE:-}" = restore-jobapp ] || { echo "Set CONFIRM_RESTORE=restore-jobapp for this destructive restore." >&2; exit 1; }
SOURCE="$(realpath "${1:?Backup directory is required}")"
: "${BACKUP_PASSPHRASE_FILE:?An existing backup decryption key is required}"
[ -f "$SOURCE/SHA256SUMS" ] || { echo "Backup manifest missing" >&2; exit 1; }
(cd "$SOURCE" && sha256sum -c SHA256SUMS)
TEMP="$(mktemp -d)"
trap 'rm -rf "$TEMP"' EXIT
for file in postgres.dump resume_storage.tar.gz risk_engine_data.tar.gz; do
  gpg --batch --yes --pinentry-mode loopback --passphrase-file "$BACKUP_PASSPHRASE_FILE" \
    --decrypt -o "$TEMP/$file" "$SOURCE/$file.gpg"
done
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"
PROJECT="${COMPOSE_PROJECT_NAME:-$(basename "$PWD" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9_-')}"
# Take a recovery point before touching the current database or protected files.
bash infra/scripts/backup-prod.sh
$COMPOSE stop backend worker scraper beat
$COMPOSE exec -T postgres pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  --clean --if-exists --single-transaction --exit-on-error < "$TEMP/postgres.dump"
for volume in resume_storage risk_engine_data; do
  # Fixed /restore mountpoint belongs only to the selected application volume.
  docker run --rm -v "${PROJECT}_${volume}:/restore" -v "$TEMP:/backup:ro" \
    alpine:3.20 sh -eu -c 'find /restore -mindepth 1 -delete; tar -C /restore -xzf "/backup/$1.tar.gz"; chown -R 1000:1000 /restore' sh "$volume"
done
bash infra/scripts/provision-db-roles.sh
$COMPOSE up -d --no-build --wait --wait-timeout 240
bash infra/scripts/verify-deploy.sh
echo "Full-platform restore verified."
