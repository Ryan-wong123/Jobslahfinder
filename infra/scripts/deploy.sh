#!/usr/bin/env bash
# Deploy a commit on the VM with pre-deploy backup, migrations, smoke test and automatic rollback.
# Usage: DEPLOY_SHA=<sha> bash infra/scripts/deploy.sh   (run from the repository on the VM)
set -Eeuo pipefail

cd "$(dirname "$0")/../.."
[ -f .env ] || { echo "Missing .env" >&2; exit 1; }
set -a; . ./.env; set +a

: "${DOMAIN:?DOMAIN must be set in .env}"
TARGET_SHA="${DEPLOY_SHA:?DEPLOY_SHA is required}"
PREVIOUS_SHA="${PREVIOUS_SHA:-$(git rev-parse HEAD)}"
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"

smoke_test() {
  for attempt in $(seq 1 30); do
    if curl -fsS --max-time 10 "https://${DOMAIN}/health" >/dev/null 2>&1; then
      echo "Smoke test passed (attempt $attempt)."
      return 0
    fi
    sleep 5
  done
  return 1
}

deploy_ref() {
  git checkout --force "$1"
  $COMPOSE build backend worker beat frontend
  $COMPOSE up -d postgres redis
  if [ "${2:-migrate}" = "migrate" ]; then
    $COMPOSE run --rm -T backend alembic upgrade head
  fi
  $COMPOSE up -d --remove-orphans
}

if [ "${SKIP_BACKUP:-0}" != "1" ] && $COMPOSE ps --status running postgres 2>/dev/null | grep -q postgres; then
  echo "Taking pre-deploy backup..."
  SUDO=""
  [ "$(id -u)" -ne 0 ] && SUDO="sudo"
  $SUDO bash infra/scripts/backup-prod.sh
fi

git fetch --prune origin
echo "Deploying $TARGET_SHA (previous: $PREVIOUS_SHA)"
if deploy_ref "$TARGET_SHA" migrate && smoke_test; then
  $COMPOSE ps
  docker image prune -f >/dev/null 2>&1 || true
  echo "Deploy succeeded."
  exit 0
fi

echo "Deploy or smoke test FAILED. Rolling back to $PREVIOUS_SHA (database migrations are NOT reverted; restore from backup if schema changed)." >&2
$COMPOSE logs --tail=80 backend nginx >&2 || true
deploy_ref "$PREVIOUS_SHA" skip || true
smoke_test || echo "Rollback smoke test failed; manual intervention required." >&2
exit 1
