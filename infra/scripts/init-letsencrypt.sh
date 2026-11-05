#!/usr/bin/env sh
# One-time Let's Encrypt bootstrap for the production compose stack.
# Run from the repository root on the VM, after DNS for $DOMAIN points at this host
# and ports 80/443 are open in the security group.
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

mkdir -p "$WWW_DIR" "$LIVE_DIR"

if [ ! -f "$LIVE_DIR/fullchain.pem" ]; then
  echo "Creating temporary self-signed certificate so Nginx can start..."
  openssl req -x509 -nodes -newkey rsa:2048 -days 1 \
    -keyout "$LIVE_DIR/privkey.pem" -out "$LIVE_DIR/fullchain.pem" \
    -subj "/CN=$DOMAIN" >/dev/null 2>&1
  touch "$LIVE_DIR/.dummy"
fi

$COMPOSE up -d postgres redis backend frontend nginx

if [ -f "$LIVE_DIR/.dummy" ]; then
  echo "Requesting Let's Encrypt certificate for $DOMAIN..."
  rm -rf "$CONF_DIR/live/$DOMAIN" "$CONF_DIR/archive/$DOMAIN" "$CONF_DIR/renewal/$DOMAIN.conf"
  $COMPOSE run --rm certbot certonly --webroot -w /var/www/certbot \
    $STAGING_FLAG --email "$LETSENCRYPT_EMAIL" --agree-tos --no-eff-email \
    -d "$DOMAIN"
fi

$COMPOSE exec -T nginx nginx -s reload
echo "Done. Test: curl -I https://$DOMAIN"
