#!/usr/bin/env bash
# Host-side health, certificate, and recovery freshness checks. Publishes a
# bounded 0/1 metric when MONITOR_CLOUDWATCH=1; never sends application data.
set -Eeuo pipefail
cd "$(dirname "$0")/../.."
set -a; . ./.env; set +a
: "${DOMAIN:?DOMAIN is required}"
failure=0
curl -fsS --max-time 10 "https://$DOMAIN/api/ready" >/dev/null || failure=1
for service in backend worker scraper beat frontend nginx redis postgres scraper-proxy; do
  container="$(docker compose ps -q "$service")"
  if [ -z "$container" ]; then failure=1; continue; fi
  state="$(docker inspect --format '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}' "$container")"
  case "$state" in 'running healthy'|'running ') ;; *) failure=1;; esac
done
latest="$(find "${BACKUP_DIR:-/var/backups/jobapp}" -mindepth 2 -maxdepth 2 -name SHA256SUMS -mmin -1560 -print -quit)"
[ -n "$latest" ] || failure=1
openssl x509 -in "infra/certbot/conf/live/$DOMAIN/cert.pem" -checkend 604800 -noout >/dev/null || failure=1
if [ "${MONITOR_CLOUDWATCH:-0}" = "1" ]; then
  aws cloudwatch put-metric-data --namespace Jobslahfinder/Operations \
    --metric-name Unhealthy --value "$failure" --unit Count \
    --dimensions "Platform=jobslahfinder"
fi
if [ "$failure" -ne 0 ]; then
  logger -p daemon.err -t jobslahfinder-monitor "Health, certificate, or daily backup check failed."
fi
exit "$failure"
