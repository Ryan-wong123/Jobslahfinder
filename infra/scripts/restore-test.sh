#!/usr/bin/env bash
# Verifies a backup is restorable by loading it into a throwaway PostgreSQL container.
# Never touches the production database.
# Usage: bash infra/scripts/restore-test.sh /var/backups/jobapp/<timestamp>
set -Eeuo pipefail
umask 077

SRC="${1:?Usage: restore-test.sh <backup-dir>}"
DUMP="$SRC/postgres.dump"
CLEANUP=""
if [ ! -f "$DUMP" ] && [ -f "$SRC/postgres.dump.gpg" ]; then
  : "${BACKUP_PASSPHRASE_FILE:?BACKUP_PASSPHRASE_FILE required for encrypted backups}"
  DUMP="$(mktemp)"; CLEANUP="$DUMP"
  gpg --batch --yes --decrypt --passphrase-file "$BACKUP_PASSPHRASE_FILE" -o "$DUMP" "$SRC/postgres.dump.gpg"
fi
[ -f "$DUMP" ] || { echo "No postgres dump found in $SRC" >&2; exit 1; }
[ -f "$SRC/SHA256SUMS" ] && (cd "$SRC" && sha256sum -c SHA256SUMS)

NAME="restore-test-$$"
trap 'docker rm -f "$NAME" >/dev/null 2>&1 || true; [ -n "$CLEANUP" ] && rm -f "$CLEANUP"' EXIT
docker run -d --name "$NAME" -e POSTGRES_PASSWORD=restoretest -e POSTGRES_DB=restore postgres:16-alpine@sha256:aa6cb33cf4c19c765cefcf48d96176258800870a9a1e930ad126200f9d825139 >/dev/null
for _ in $(seq 1 30); do docker exec "$NAME" pg_isready -U postgres >/dev/null 2>&1 && break; sleep 1; done
docker exec -i "$NAME" pg_restore -U postgres -d restore --no-owner --exit-on-error < "$DUMP"

TABLES="$(docker exec "$NAME" psql -U postgres -d restore -tAc "select count(*) from information_schema.tables where table_schema='public'")"
USERS="$(docker exec "$NAME" psql -U postgres -d restore -tAc "select count(*) from users")"
echo "Restore OK: $TABLES public tables, $USERS users."
[ "$TABLES" -ge 10 ] || { echo "Unexpectedly few tables; restore suspect." >&2; exit 1; }
