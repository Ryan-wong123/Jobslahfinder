# Security Hardening Notes

## HTTPS/TLS Local Testing

Nginx includes security headers and request body limits for the coursework MVP. For local TLS testing, the Dockerized Nginx reverse proxy can terminate HTTPS with a self-signed certificate.

This repository includes local self-signed TLS files:

- `docker-compose.local-tls.yml` exposes Nginx on `80` for HTTP and `443` for HTTPS.
- `infra/nginx/local-tls.conf` redirects HTTP to HTTPS and proxies frontend/backend traffic after TLS termination.
- `infra/scripts/create-local-cert.ps1` generates `localhost.crt` and `localhost.key` for local testing.
- `infra/nginx/certs/` stores generated local certificate files and is ignored by Git except for `.gitkeep`.

Create the local certificate from Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\infra\scripts\create-local-cert.ps1
```

Start the app with local HTTPS:

```powershell
docker compose -f docker-compose.yml -f docker-compose.local-tls.yml up -d --build
```

Verify:

```powershell
curl.exe -k -I https://localhost
curl.exe -k -I https://localhost/health
curl.exe -I http://localhost
```

Expected results:

- `https://localhost` returns the frontend.
- `https://localhost/health` reaches the backend through Nginx.
- `http://localhost` redirects to `https://localhost`.

The certificate is self-signed, so browser warnings are expected. Do not use the self-signed certificate for public production deployment.

## Logs And Sensitive Data

Application audit logs must remain metadata-only. Do not log passwords, password hashes, raw tokens, API keys, raw prompts, resume contents, generated cover letter text, edited cover letter text, environment variables, or internal stack traces to user-facing responses. Admin audit-log responses filter sensitive audit detail keys before display and should bound nested detail string lengths to prevent log bloat.

Runtime logs should be written to restricted host or container log storage, not to `frontend/public`, `.next`, `infra/nginx/html`, or any other public web directory.

Resume extraction paths must not print raw extracted resume text, including local debugging output for AI-backed extraction.

## Input Validation Hardening

Backend validation must remain the enforcement point. Public job browsing should only expose active, non-suspicious postings; inactive and suspicious job filters belong behind admin-only job moderation routes.

Password reset tokens should use strict allowlist validation that matches the generated token format. Resource IDs should use positive integer path constraints consistently across normal and admin routes.

Resume uploads should validate extension, declared MIME type, content-derived type or signature, file size, filename safety, and path traversal. DOCX handling should also enforce archive safety limits such as maximum entry count, maximum total uncompressed bytes, and maximum compression ratio.

External job URLs should be HTTPS-only, belong to the approved source domain allowlist, and reject credentialed, malformed, or excessively long URLs. Structured AI output such as interview questions should be validated against explicit response schemas before it is returned or stored.

## Backups And Restore

`infra/scripts/backup.sh` creates a PostgreSQL dump and optional protected upload/log archives in `BACKUP_DIR`, defaulting to `/var/backups/jobapp`. The directory is created with owner-only permissions and should be mounted to protected storage, not served by Nginx.

`infra/scripts/restore.sh` restores a selected backup directory. Run restore tests on a non-production database before relying on a backup for deployment recovery.

Example container usage:

```sh
docker compose exec postgres sh /infra/scripts/backup.sh
BACKUP_PATH=/var/backups/jobapp/20260502T120000Z docker compose exec postgres sh /infra/scripts/restore.sh
```

Mount the scripts and backup directory into the appropriate maintenance container before running these commands in production.

## Production Profile Controls

- **TLS:** `infra/nginx/templates/production.conf.template` serves HTTPS (TLS 1.2/1.3) with Let's Encrypt certificates, redirects HTTP to HTTPS, sends HSTS, and returns 444 for requests that do not use the configured hostname.
- **Rate limiting:** Nginx limits `/api/auth/*` (30 req/min per IP, burst 10) and `/api/*` (20 req/s), on top of application-level limits. Requests over the limit get HTTP 429.
- **Proxy trust:** Nginx overwrites `X-Forwarded-For` with the real client address, and the backend trusts only the Compose subnet (`172.28.0.0/24`).
- **Startup validation:** in `APP_ENV=production` the backend refuses to start with placeholder or short secrets, identical session/reset secrets, non-HTTPS or localhost `FRONTEND_BASE_URL`, `DEBUG=true`, or missing SMTP/Gemini configuration.
- **Resource safety:** per-service memory limits, log rotation (10 MB x 5), and healthchecks for every service.

## Accepted Risks And Limitations

- **CSP `script-src 'unsafe-inline'`:** required by Next.js inline hydration scripts. Mitigated by output encoding of untrusted content, `object-src 'none'`, `frame-ancestors 'none'` and `base-uri 'self'`. A nonce-based CSP via Next.js middleware is a future hardening item.
- **Migrations are not auto-reverted on rollback:** deploy.sh restores code only; use the pre-deploy backup for schema recovery.
- **Image tags are pinned by version, not digest.**
- **Scraping depends on third-party site layout and terms:** review each source's terms of service/robots.txt before enabling it in production and monitor scraping runs in `/admin`.
- **GeoLite2 database is optional** and must be downloaded by the operator.
