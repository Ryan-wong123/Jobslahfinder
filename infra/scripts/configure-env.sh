#!/usr/bin/env bash
# Fill the production .env: domain, public URL, Let's Encrypt email and fresh random secrets.
# Safe to re-run: secrets that are already set (not placeholders) are never changed.
#
# Usage (from the repository root on the server):
#   DOMAIN=jobs.example.com EMAIL=you@example.com bash infra/scripts/configure-env.sh
#   Optional: S3URI=s3://my-bucket/jobapp   (off-server backups)
#
# You still add SMTP_* and GEMINI_API_KEY yourself (nano .env). Nothing secret is printed.
set -Eeuo pipefail
cd "$(dirname "$0")/../.."

: "${DOMAIN:?Set DOMAIN, e.g. DOMAIN=jobs.example.com}"
: "${EMAIL:?Set EMAIL (used for certificate expiry notices)}"
S3URI="${S3URI:-}"

[[ "$DOMAIN" =~ ^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$ ]] || { echo "DOMAIN looks invalid: $DOMAIN" >&2; exit 1; }
[[ "$EMAIL" =~ ^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$ ]] || { echo "EMAIL looks invalid." >&2; exit 1; }
if [ -n "$S3URI" ]; then
  [[ "$S3URI" =~ ^s3://[a-z0-9][a-z0-9.-]{2,62}(/[A-Za-z0-9._/-]*)?$ ]] || { echo "S3URI looks invalid." >&2; exit 1; }
fi

[ -f .env ] || cp .env.example .env
chmod 600 .env

get_env() { grep -m1 "^$1=" .env | cut -d= -f2- || true; }
set_env() {
  if grep -q "^$1=" .env; then
    sed -i "s|^$1=.*|$1=$2|" .env
  else
    printf '%s=%s\n' "$1" "$2" >> .env
  fi
}
is_placeholder() { case "$(get_env "$1")" in ""|*change-me*|*replace-with*|*placeholder*) return 0;; *) return 1;; esac; }

set_env DOMAIN "$DOMAIN"
set_env FRONTEND_BASE_URL "https://$DOMAIN"
set_env LETSENCRYPT_EMAIL "$EMAIL"
set_env COMPOSE_FILE "docker-compose.yml:docker-compose.prod.yml"
[ -z "$S3URI" ] || set_env BACKUP_S3_URI "$S3URI"

if is_placeholder POSTGRES_PASSWORD; then
  # A new database password only works with a brand-new database volume.
  if [ "${FORCE:-0}" != "1" ] && command -v docker >/dev/null 2>&1 \
     && docker volume ls -q 2>/dev/null | grep -q 'postgres_data$'; then
    echo "A Postgres data volume already exists, so a new POSTGRES_PASSWORD would lock the app out of it." >&2
    echo "Refusing. Set FORCE=1 only if you are sure the database can be recreated." >&2
    exit 1
  fi
  PGPASS="$(openssl rand -hex 24)"
  set_env POSTGRES_PASSWORD "$PGPASS"
  set_env DATABASE_URL "postgresql+psycopg://$(get_env POSTGRES_USER):$PGPASS@postgres:5432/$(get_env POSTGRES_DB)"
  echo "Generated POSTGRES_PASSWORD and DATABASE_URL."
fi
if is_placeholder SESSION_SECRET; then
  set_env SESSION_SECRET "$(openssl rand -base64 48 | tr -d '\n')"
  echo "Generated SESSION_SECRET."
fi
if is_placeholder PASSWORD_RESET_SECRET; then
  set_env PASSWORD_RESET_SECRET "$(openssl rand -base64 48 | tr -d '\n')"
  echo "Generated PASSWORD_RESET_SECRET."
fi

# Preserve the existing administrator DSN before switching application roles.
if is_placeholder MIGRATION_DATABASE_URL; then
  existing_dsn="$(get_env DATABASE_URL)"
  case "$existing_dsn" in
    *change-me*|*jobapp_runtime*|'')
      encoded_password="$(POSTGRES_PASSWORD="$(get_env POSTGRES_PASSWORD)" python3 -c 'import os,urllib.parse;print(urllib.parse.quote(os.environ["POSTGRES_PASSWORD"],safe=""))')"
      set_env MIGRATION_DATABASE_URL "postgresql+psycopg://$(get_env POSTGRES_USER):$encoded_password@postgres:5432/$(get_env POSTGRES_DB)"
      ;;
    *) set_env MIGRATION_DATABASE_URL "$existing_dsn" ;;
  esac
fi
for key in APP_DB_PASSWORD SCRAPER_DB_PASSWORD WORKER_DB_PASSWORD DATA_ENCRYPTION_SECRET REDIS_PASSWORD AUTH_REDIS_PASSWORD; do
  if is_placeholder "$key"; then set_env "$key" "$(openssl rand -hex 32)"; fi
done
set_env DATABASE_URL "postgresql+psycopg://jobapp_runtime:$(get_env APP_DB_PASSWORD)@postgres:5432/$(get_env POSTGRES_DB)"
set_env SCRAPER_DATABASE_URL "postgresql+psycopg://jobapp_scraper:$(get_env SCRAPER_DB_PASSWORD)@postgres:5432/$(get_env POSTGRES_DB)"
set_env WORKER_DATABASE_URL "postgresql+psycopg://jobapp_worker:$(get_env WORKER_DB_PASSWORD)@postgres:5432/$(get_env POSTGRES_DB)"
set_env REDIS_URL "redis://broker:$(get_env REDIS_PASSWORD)@redis:6379/0"
set_env AUTH_REDIS_URL "redis://auth:$(get_env AUTH_REDIS_PASSWORD)@redis:6379/1"

echo "Done. These settings still hold placeholders and need your real values (values hidden):"
grep -nE 'change-me|your-domain|example' .env | sed -E 's/=.*/=<hidden>/' || echo "  (none)"
