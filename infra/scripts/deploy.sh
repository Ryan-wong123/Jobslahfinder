#!/usr/bin/env bash
# Deploy only CI-scanned image digests; preserve previous images for rollback.
set -Eeuo pipefail
umask 077
cd "$(dirname "$0")/../.."
: "${DEPLOY_SHA:?DEPLOY_SHA is required}"
[[ "$DEPLOY_SHA" =~ ^[0-9a-f]{40}$ ]] || exit 1
for name in BACKEND_IMAGE FRONTEND_IMAGE SCRAPER_IMAGE; do
  [[ "${!name:-}" =~ ^ghcr\.io/[a-z0-9._/-]+@sha256:[0-9a-f]{64}$ ]] || { echo "Scanned image digest missing: $name" >&2; exit 1; }
done
RELEASE_BACKEND_IMAGE="$BACKEND_IMAGE"
RELEASE_FRONTEND_IMAGE="$FRONTEND_IMAGE"
RELEASE_SCRAPER_IMAGE="$SCRAPER_IMAGE"
[ -f .env ] || { echo "Missing .env" >&2; exit 1; }
set -a; . ./.env; set +a
: "${DOMAIN:?DOMAIN is required}"
: "${MIGRATION_DATABASE_URL:?Run configure-env.sh before this release}"
PREVIOUS_SHA="${PREVIOUS_SHA:-$(git rev-parse HEAD)}"
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"
# The named worker policy must be loaded before replacing any service.
sudo -n bash infra/scripts/install-sandbox-apparmor.sh --require
mkdir -p .releases
# A legacy release has a different Redis/worker/environment contract. Never
# pretend its images can roll back safely under the new security architecture.
if [ -f .release.env ] && grep -qx 'ROLE_CONTRACT=security-v1' .release.env; then
  cp .release.env .releases/previous.env
else
  : > .releases/previous.env
fi
export BACKEND_IMAGE="$RELEASE_BACKEND_IMAGE" FRONTEND_IMAGE="$RELEASE_FRONTEND_IMAGE" SCRAPER_IMAGE="$RELEASE_SCRAPER_IMAGE"
# Registry read credentials, if needed, are provisioned on the host separately.
$COMPOSE pull backend frontend scraper postgres redis nginx scraper-proxy
PREDEPLOY_BACKUP_TAKEN=0
if $COMPOSE ps --status running postgres 2>/dev/null | grep -q postgres; then
  sudo -n bash infra/scripts/backup-prod.sh
  PREDEPLOY_BACKUP_TAKEN=1
fi

smoke_test() {
  for attempt in $(seq 1 24); do
    if curl -fsS --max-time 5 "https://${DOMAIN}/api/ready" >/dev/null; then
      bash infra/scripts/verify-deploy.sh
      return $?
    fi
    sleep 5
  done
  return 1
}

deploy_release() {
  $COMPOSE up -d postgres redis || return 1
  # Only this disposable migration process receives administrator credentials.
  DATABASE_URL="$MIGRATION_DATABASE_URL" $COMPOSE run --rm -T --no-deps -e DATABASE_URL backend alembic upgrade head || return 1
  bash infra/scripts/provision-db-roles.sh || return 1
  $COMPOSE up -d --no-build --wait --wait-timeout 240 --remove-orphans || return 1
  if [ "$PREDEPLOY_BACKUP_TAKEN" = 0 ]; then
    sudo -n bash infra/scripts/backup-prod.sh || return 1
  fi
  smoke_test
}

persist_image_refs() {
  for key in BACKEND_IMAGE FRONTEND_IMAGE SCRAPER_IMAGE; do
    if grep -q "^$key=" .env; then
      sed -i "s|^$key=.*|$key=${!key}|" .env
    else
      printf '%s=%s\n' "$key" "${!key}" >> .env
    fi
  done
  chmod 600 .env
}

if deploy_release; then
  printf 'ROLE_CONTRACT=security-v1\nBACKEND_IMAGE=%s\nFRONTEND_IMAGE=%s\nSCRAPER_IMAGE=%s\n' "$BACKEND_IMAGE" "$FRONTEND_IMAGE" "$SCRAPER_IMAGE" > .release.env
  cp .release.env ".releases/$DEPLOY_SHA.env"
  persist_image_refs
  echo "Deployment verified. Previous images retained for rollback."
  exit 0
fi

echo "Deployment failed. Additive migrations and current infrastructure configuration are retained." >&2
if [ -s .releases/previous.env ]; then
  set -a; . .releases/previous.env; set +a
  if $COMPOSE up -d --no-deps --no-build --pull never --wait --wait-timeout 240 backend worker scraper beat frontend; then
    cp .releases/previous.env .release.env
    persist_image_refs
  else
    $COMPOSE stop backend worker scraper beat || true
    echo "Compatible-image rollback failed; application writers stopped for recovery." >&2
  fi
else
  $COMPOSE stop backend worker scraper beat || true
  echo "No compatible security-v1 release exists. Application writers stopped; restore the protected pre-upgrade backup/configuration or roll forward." >&2
fi
exit 1
