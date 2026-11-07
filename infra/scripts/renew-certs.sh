#!/usr/bin/env sh
# Renew Let's Encrypt certificates and reload Nginx. Schedule twice daily, e.g. in root's crontab:
#   17 3,15 * * * cd /opt/jobslahfinder && sh infra/scripts/renew-certs.sh >> /var/log/jobapp-cert-renew.log 2>&1
set -eu
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"
$COMPOSE run --rm certbot renew --webroot -w /var/www/certbot --quiet
$COMPOSE exec -T nginx nginx -s reload
