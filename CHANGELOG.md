# Changelog

## Production readiness (branch `production`)

### Added
- `docker-compose.prod.yml`: ports 80/443, log rotation, memory limits, worker/beat healthchecks, narrowed trusted-proxy subnet.
- `infra/nginx/templates/production.conf.template`: Let's Encrypt TLS, HTTP->HTTPS redirect, HSTS, auth/API rate limiting, gzip, timeouts, static caching.
- Scripts: `init-letsencrypt.sh`, `renew-certs.sh`, `backup-prod.sh` (encrypted, S3 off-box), `restore-test.sh`, `deploy.sh` (backup, migrate, smoke test, rollback), `download-geolite.sh`.
- CI: 70% coverage gate, production compose and Nginx config validation, script syntax checks.
- Startup validation tests for production configuration.

### Changed
- `FRONTEND_BASE_URL` no longer defaults to a public IP; production requires an https, non-localhost URL.
- Production refuses placeholder secrets and identical session/reset secrets.
- Deploy job now uses `infra/scripts/deploy.sh` with automatic code rollback.
- `.env.example` and deployment docs rewritten for the domain + TLS flow.

### Removed
- Tracked `cookies.txt`, `frontend/.env.local`, `tsconfig.tsbuildinfo`, `GeoLite2-City.mmdb`, `railway-preview.json`.
