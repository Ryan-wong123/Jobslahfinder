#!/usr/bin/env bash
# Host-side backup for the production compose stack.
# Dumps PostgreSQL, archives resume storage + risk-engine data, requires encryption
# (BACKUP_PASSPHRASE_FILE) and copies off-box to S3 (BACKUP_S3_URI).
#
# Cron example (daily 02:30, root):
#   30 2 * * * cd /opt/jobslahfinder && bash infra/scripts/backup-prod.sh >> /var/log/jobapp-backup.log 2>&1
set -Eeuo pipefail
umask 077

cd "$(dirname "$0")/../.."
set -a; . ./.env; set +a
if [ "$#" -gt 0 ]; then
  [[ "$#" -eq 1 && "$1" =~ ^ghcr\.io/[a-z0-9._/-]+@sha256:[0-9a-f]{64}$ ]] || {
    echo "Expected one scanned backend image digest." >&2
    exit 1
  }
  export BACKEND_IMAGE="$1"
fi

COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/jobapp}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DEST="$BACKUP_DIR/$STAMP"
PROJECT="${COMPOSE_PROJECT_NAME:-$(basename "$PWD" | tr "[:upper:]" "[:lower:]" | tr -cd "a-z0-9_-")}"

[ -n "${BACKUP_PASSPHRASE_FILE:-}" ] && [ -r "$BACKUP_PASSPHRASE_FILE" ] || {
  echo "An existing protected BACKUP_PASSPHRASE_FILE is required." >&2; exit 1;
}
[[ "$BACKUP_DIR" = /* && "$BACKUP_DIR" != / ]] || { echo "Invalid backup root" >&2; exit 1; }
[[ "$RETENTION_DAYS" =~ ^[0-9]+$ ]] || exit 1
mkdir -p "$DEST"
chmod 700 "$BACKUP_DIR" "$DEST"

# Quiesce writers briefly so the database and protected files describe the same
# point in time. Resume exactly the services that were running, even on failure.
mapfile -t WRITERS < <($COMPOSE ps --services --status running | grep -E '^(backend|worker|scraper|beat)$' || true)
resume_writers() { if [ "${#WRITERS[@]}" -gt 0 ]; then $COMPOSE start "${WRITERS[@]}"; fi; }
trap resume_writers EXIT
if [ "${#WRITERS[@]}" -gt 0 ]; then $COMPOSE stop "${WRITERS[@]}"; fi

echo "[$STAMP] Dumping PostgreSQL..."
$COMPOSE exec -T postgres pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc > "$DEST/postgres.dump"

echo "[$STAMP] Archiving resume storage and risk-engine data..."
# SQLite must be backed up through its backup API, not copied mid-transaction.
$COMPOSE run --rm -T --no-deps --pull never backend python - < backend/app/workers/backup_risk.py > "$DEST/risk_engine_data.tar.gz"
for vol in resume_storage; do
  docker run --rm -v "${PROJECT}_${vol}:/data:ro" -v "$DEST:/out" alpine:3.20 \
    tar -C /data -czf "/out/${vol}.tar.gz" .
done

resume_writers
trap - EXIT

if [ -n "${BACKUP_PASSPHRASE_FILE:-}" ]; then
  echo "[$STAMP] Encrypting backup files..."
  for f in "$DEST"/*.dump "$DEST"/*.tar.gz; do
    gpg --batch --yes --pinentry-mode loopback --symmetric --cipher-algo AES256 --passphrase-file "$BACKUP_PASSPHRASE_FILE" -o "$f.gpg" "$f"
    shred -u "$f" 2>/dev/null || rm -f "$f"
  done
fi

sha256sum "$DEST"/* > "$DEST/SHA256SUMS"
chmod -R go-rwx "$DEST"

if [ -n "${BACKUP_S3_URI:-}" ]; then
  echo "[$STAMP] Uploading to $BACKUP_S3_URI ..."
  aws s3 cp --recursive --sse AES256 "$DEST" "${BACKUP_S3_URI%/}/$STAMP/"
fi

find "$BACKUP_DIR" -mindepth 1 -maxdepth 1 -type d -mtime +"$RETENTION_DAYS" -exec rm -rf {} +
echo "[$STAMP] Backup complete: $DEST"
