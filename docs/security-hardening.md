# Security Hardening Notes

## Optional Self-Signed HTTPS

The default deployment still uses the existing HTTP path. HTTPS is opt-in through `docker-compose.local-tls.yml`.

For local Windows testing:

```powershell
powershell -ExecutionPolicy Bypass -File .\infra\scripts\create-local-cert.ps1
docker compose -f docker-compose.yml -f docker-compose.local-tls.yml up -d --build
```

For an EC2 IP-only project demo:

```sh
sh ./infra/scripts/create-ec2-self-signed-cert.sh EC2_PUBLIC_IP
docker compose -f docker-compose.yml -f docker-compose.local-tls.yml up -d --build
```

Then browse to:

```text
https://EC2_PUBLIC_IP
```

Browser warnings are expected because the certificate is self-signed. This encrypts traffic for a project demo, but it is not a publicly trusted production TLS setup.

Only set these EC2 `.env` values after HTTPS is actually working:

```env
APP_ENV=production
FRONTEND_BASE_URL=https://EC2_PUBLIC_IP
```

Do not commit generated `.crt`, `.key`, or OpenSSL config files from `infra/nginx/certs/`.

## Backups And Restore

`infra/scripts/backup.sh` creates:

- a PostgreSQL custom dump
- an optional protected resume storage archive
- an optional app log archive

The default backup directory is `/var/backups/jobapp`. Keep it outside any Nginx public directory.

Example:

```sh
docker compose exec postgres sh /infra/scripts/backup.sh
```

`infra/scripts/restore.sh` restores a backup directory selected by `BACKUP_PATH`:

```sh
BACKUP_PATH=/var/backups/jobapp/20260630T120000Z docker compose exec postgres sh /infra/scripts/restore.sh
```

Test restores on a non-production database before relying on backups.

## Risk Engine

The risk engine is mounted at:

```text
/risk-engine
```

The human dashboard requires a valid main-app admin session and two-factor authentication. The machine API uses the risk engine API key after setup.

Risk engine state is stored in `RISK_ENGINE_DATA_DIR`, defaulted in Docker to:

```text
/var/lib/jobapp/risk-engine
```

Keep that directory private and backed up. It may contain engine state, SQLite risk data, and audit data.
