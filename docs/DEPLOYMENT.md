# Production Deployment (EC2, Docker Compose, Let's Encrypt)

Production runs `docker-compose.yml` + `docker-compose.prod.yml`: Nginx terminates HTTPS on 80/443, everything else stays on the internal Docker network. CI/CD (`.github/workflows/ci-cd.yml`) deploys with `infra/scripts/deploy.sh`, which takes a pre-deploy backup, migrates, smoke-tests `https://$DOMAIN/health`, and rolls the code back automatically on failure.

## 1. Prerequisites

- An EC2 instance (Ubuntu recommended) with Docker, Docker Compose v2, Git, `curl`, `openssl`, and optionally `awscli` and `gpg` (for off-box encrypted backups).
- A DNS `A` record for your domain pointing at the instance's public IP (use an Elastic IP).
- Security group: `80` and `443` open to the world; `22` restricted to trusted IPs. Do **not** open 5432, 6379 or 8000.

## 2. GitHub secrets (Settings -> Secrets and variables -> Actions)

| Secret | Notes |
| --- | --- |
| `EC2_HOST` | Public IP or DNS of the instance. |
| `EC2_USER` | SSH user (`ubuntu` / `ec2-user`). |
| `EC2_PORT` | Optional, defaults to `22`. |
| `EC2_SSH_KEY` | Full private key (never stored on the VM). |
| `DEPLOY_PATH` | Absolute path of the checkout, e.g. `/opt/jobslahfinder`. |

## 3. Configure the VM

Shortcut: `bash infra/scripts/bootstrap-vm.sh` installs Docker, AWS CLI and git, creates the protected backup directory, enables automatic security updates, installs the backup and certificate-renewal cron jobs, and creates `.env` from the template. After step 6 run `bash infra/scripts/verify-deploy.sh` to check DNS, HTTPS, headers, closed ports and config in one go.

```bash
sudo mkdir -p /opt/jobslahfinder && sudo chown "$USER" /opt/jobslahfinder
git clone <repo-url> /opt/jobslahfinder && cd /opt/jobslahfinder
cp .env.example .env && chmod 600 .env
```

Edit `.env` and replace **every** placeholder. In production the backend refuses to start if:
`FRONTEND_BASE_URL` is not `https://` or points at localhost, any secret still contains a placeholder (`change-me`, `replace-with`, ...), the session and reset secrets are identical or shorter than 32 characters, SMTP is not configured, or Gemini is enabled without an API key.

Generate secrets with `openssl rand -base64 48`. Required deployment keys: `DOMAIN`, `LETSENCRYPT_EMAIL`, `FRONTEND_BASE_URL=https://<DOMAIN>`, `COMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml`, `POSTGRES_*`, `DATABASE_URL`, `SESSION_SECRET`, `PASSWORD_RESET_SECRET`, SMTP_*, `GEMINI_API_KEY`.

Use a transactional email provider (e.g. Amazon SES) and configure SPF/DKIM for your domain, otherwise password-reset email will be filtered as spam.

## 4. First-time HTTPS and startup

```bash
sh infra/scripts/init-letsencrypt.sh        # set LETSENCRYPT_STAGING=1 first to test without rate limits
docker compose run --rm backend alembic upgrade head
docker compose run --rm backend python -m app.cli create-initial-admin --email admin@your-domain
```

Schedule certificate renewal (twice daily) in root's crontab:

```cron
17 3,15 * * * cd /opt/jobslahfinder && sh infra/scripts/renew-certs.sh >> /var/log/jobapp-cert-renew.log 2>&1
```

### Optional GeoIP database

The risk engine's impossible-travel check uses MaxMind GeoLite2 (not committed; licence forbids redistribution). Without it that check is skipped.

```bash
MAXMIND_LICENSE_KEY=<your key> sh infra/scripts/download-geolite.sh   # writes infra/geoip/GeoLite2-City.mmdb
docker compose up -d backend
```

Initialise the risk engine once and store the returned key in a password manager: `curl -X POST https://<DOMAIN>/risk-engine/setup`.

## 5. Backups and restore test

```cron
30 2 * * * cd /opt/jobslahfinder && bash infra/scripts/backup-prod.sh >> /var/log/jobapp-backup.log 2>&1
```

Environment (export in the cron line or `/etc/environment`): `BACKUP_DIR` (default `/var/backups/jobapp`), `BACKUP_RETENTION_DAYS` (14), `BACKUP_PASSPHRASE_FILE` (enables GPG AES-256 encryption), `BACKUP_S3_URI` (e.g. `s3://my-bucket/jobapp`, uploaded with server-side encryption; give the instance an IAM role limited to that prefix).

Verify a backup is restorable (runs in a throwaway container, never touches production):

```bash
bash infra/scripts/restore-test.sh /var/backups/jobapp/<timestamp>
```

Run this after the first backup and periodically afterwards; record the result in `docs/TASKS.md`.

## 6. Deploying

Push to `main` (or run the workflow manually). The deploy job runs `infra/scripts/deploy.sh`: backup -> checkout -> build -> `alembic upgrade head` -> start -> HTTPS `/health` smoke test -> rollback of the code on failure. Migrations are not reverted on rollback; restore the pre-deploy backup if a schema change must be undone.

Manual deploy on the VM: `DEPLOY_SHA=$(git rev-parse origin/main) bash infra/scripts/deploy.sh`.

## 7. Post-deploy verification

```bash
docker compose ps                              # all services healthy
curl -sI https://<DOMAIN> | head              # HSTS + CSP headers present
curl -sI http://<DOMAIN> | head -1            # 301 to https
curl -s -o /dev/null -w '%{http_code}\n' https://<DOMAIN>/api/me   # 401 when logged out
nmap -Pn -p 5432,6379,8000 <public-ip>        # must all be closed/filtered
```

## Self-signed HTTPS for an IP-only demo (not for production)

```bash
sh ./infra/scripts/create-ec2-self-signed-cert.sh <EC2_PUBLIC_IP>
docker compose -f docker-compose.yml -f docker-compose.local-tls.yml up -d --build
```
