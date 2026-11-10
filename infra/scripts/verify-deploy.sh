#!/usr/bin/env bash
# Post-deploy verification. Run on the VM from the repository root.
set -uo pipefail
cd "$(dirname "$0")/../.."
[ -f .env ] || { echo "FAIL .env missing"; exit 1; }
set -a; . ./.env; set +a
: "${DOMAIN:?DOMAIN not set in .env}"

PASS=0; FAILN=0
ok()   { echo "PASS  $1"; PASS=$((PASS+1)); }
bad()  { echo "FAIL  $1"; FAILN=$((FAILN+1)); }
check(){ if eval "$2" >/dev/null 2>&1; then ok "$1"; else bad "$1"; fi; }

PUBLIC_IP="$(curl -fsS --max-time 5 https://checkip.amazonaws.com 2>/dev/null | tr -d '[:space:]')"
DNS_IP="$(getent hosts "$DOMAIN" | awk '{print $1; exit}')"
check "DNS for $DOMAIN resolves to this VM ($PUBLIC_IP)" '[ -n "$PUBLIC_IP" ] && [ "$DNS_IP" = "$PUBLIC_IP" ]'
check ".env permissions are 600" '[ "$(stat -c %a .env)" = "600" ]'
check "Backend config validates (no placeholder secrets)" \
  'docker compose run --rm --no-deps backend python -c "from app.core.config import get_settings; get_settings()"'
check "All compose services running" '[ -z "$(docker compose ps --format "{{.Service}} {{.Status}}" | grep -viE "up|healthy|running" )" ]'
check "No unhealthy containers" '! docker compose ps | grep -qi unhealthy'
for service in backend worker scraper beat frontend nginx redis postgres scraper-proxy; do
  check "$service container exists" '[ -n "$(docker compose ps -q "$service")" ]'
done
check "HTTP redirects to HTTPS (301)" '[ "$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 http://$DOMAIN/)" = "301" ]'
check "HTTPS certificate is valid" 'curl -fsS --max-time 10 -o /dev/null https://$DOMAIN/'
check "HSTS header present" 'curl -sI --max-time 10 https://$DOMAIN/ | grep -qi "^strict-transport-security"'
check "CSP header present" 'curl -sI --max-time 10 https://$DOMAIN/ | grep -qi "^content-security-policy"'
check "Backend /health returns 200" '[ "$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 https://$DOMAIN/health)" = "200" ]'
check "Dependency readiness returns 200" 'curl -fsS --max-time 10 https://$DOMAIN/api/ready'
for path in / /api/jobs /api/me /risk-engine/admin/; do
  for header in content-security-policy x-content-type-options x-frame-options referrer-policy permissions-policy strict-transport-security; do
    check "$path includes $header" 'curl -sD - -o /dev/null --max-time 10 "https://$DOMAIN$path" | grep -qi "^$header:"'
  done
done
check "Risk setup cannot initialize over HTTP" '[ "$(curl -s -X POST -o /dev/null -w "%{http_code}" --max-time 10 https://$DOMAIN/risk-engine/setup)" = "404" ]'
check "/api/me is 401 when logged out" '[ "$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 https://$DOMAIN/api/me)" = "401" ]'
check "API docs are not exposed (/docs is not 200)" '[ "$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 https://$DOMAIN/api/docs)" != "200" ]'
check "Server version hidden" '! curl -sI --max-time 10 https://$DOMAIN/ | grep -i "^server:" | grep -qE "[0-9]\.[0-9]"'
check "Uploads not web-accessible" '[ "$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 https://$DOMAIN/uploads/)" != "200" ]'
for port in 5432 6379 8000; do
  check "Port $port closed on public IP" '! timeout 3 bash -c "echo > /dev/tcp/$PUBLIC_IP/$port"'
done
check "Backup directory is private (700)" '[ "$(stat -c %a /var/backups/jobapp 2>/dev/null)" = "700" ]'
check "Cron jobs installed" 'sudo -n crontab -l | grep -q backup-prod.sh && sudo -n crontab -l | grep -q renew-certs.sh && sudo -n crontab -l | grep -q monitor.sh'

echo; echo "Result: $PASS passed, $FAILN failed"
echo "Also test from ANOTHER machine: nmap -Pn -p 22,80,443,5432,6379,8000 $PUBLIC_IP"
[ "$FAILN" -eq 0 ]
