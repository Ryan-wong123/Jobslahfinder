#!/usr/bin/env sh
# One-time Let's Encrypt bootstrap for the production compose stack.
# Run from the repository root on the VM, after DNS for $DOMAIN points at this host
# and ports 80/443 are open in the security group.
# Set LETSENCRYPT_STAGING=1 for a dry run against Let's Encrypt's staging server.
set -eu

[ -f .env ] || { echo ".env not found. Create it first." >&2; exit 1; }
set -a; . ./.env; set +a
: "${DOMAIN:?DOMAIN must be set in .env}"
: "${LETSENCRYPT_EMAIL:?LETSENCRYPT_EMAIL must be set in .env}"

COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"
CONF_DIR="infra/certbot/conf"
WWW_DIR="infra/certbot/www"
LIVE_DIR="$CONF_DIR/live/$DOMAIN"
STAGING_FLAG=""
[ "${LETSENCRYPT_STAGING:-0}" = "1" ] && STAGING_FLAG="--staging"

make_dummy_cert() {
  mkdir -p "$LIVE_DIR"
  openssl req -x509 -nodes -newkey rsa:2048 -days 1 \
    -keyout "$LIVE_DIR/privkey.pem" -out "$LIVE_DIR/fullchain.pem" \
    -subj "/CN=$DOMAIN" >/dev/null 2>&1
  touch "$LIVE_DIR/.dummy"
}

wait_for_nginx() {
  i=0
  while [ "$i" -lt 30 ]; do
    if curl -s -o /dev/null --max-time 3 "http://127.0.0.1/.well-known/acme-challenge/ping"; then
      return 0
    fi
    i=$((i+1)); sleep 2
  done
  echo "Nginx is not answering on port 80. Recent logs:" >&2
  $COMPOSE logs --tail=30 nginx >&2 || true
  return 1
}

mkdir -p "$WWW_DIR"
if [ ! -f "$LIVE_DIR/fullchain.pem" ]; then
  echo "Creating temporary self-signed certificate so Nginx can start..."
  make_dummy_cert
fi

$COMPOSE up -d postgres redis backend frontend
# Recreate Nginx so its bind mounts point at the current certificate folder.
$COMPOSE up -d --no-deps --force-recreate nginx
wait_for_nginx

if [ -f "$LIVE_DIR/.dummy" ]; then
  echo "Requesting Let's Encrypt certificate for $DOMAIN..."
  rm -rf "$CONF_DIR/live/$DOMAIN" "$CONF_DIR/archive/$DOMAIN" "$CONF_DIR/renewal/$DOMAIN.conf"
  if ! $COMPOSE run --rm certbot certonly --webroot -w /var/www/certbot \
        $STAGING_FLAG --email "$LETSENCRYPT_EMAIL" --agree-tos --no-eff-email \
        -d "$DOMAIN"; then
    echo "Certificate request FAILED. Restoring the temporary certificate so Nginx keeps running." >&2
    make_dummy_cert
    $COMPOSE exec -T nginx nginx -s reload || $COMPOSE up -d --no-deps --force-recreate nginx
    echo "Fix the cause above, then re-run this script." >&2
    exit 1
  fi
fi

$COMPOSE exec -T nginx nginx -s reload
echo "Done. Test: curl -I https://$DOMAIN"
