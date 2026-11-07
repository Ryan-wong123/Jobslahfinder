# Production Deployment (EC2, Docker Compose, Let's Encrypt)

Production runs `docker-compose.yml` + `docker-compose.prod.yml`: Nginx terminates HTTPS on 80/443, everything else stays on the internal Docker network. CI/CD (`.github/workflows/ci-cd.yml`) deploys through AWS Systems Manager (`infra/scripts/ssm-deploy.sh`), which runs `infra/scripts/deploy.sh` on the instance. That script takes a pre-deploy backup, migrates, smoke-tests `https://$DOMAIN/health`, and rolls the code back automatically on failure.

## 1. Prerequisites

- An EC2 instance (Ubuntu recommended) with Docker, Docker Compose v2, Git, `curl`, `openssl`, and optionally `awscli` and `gpg` (for off-box encrypted backups). `infra/scripts/bootstrap-vm.sh` installs these.
- A DNS `A` record for your domain pointing at the instance's public IP (use an Elastic IP).
- Security group: `80` and `443` open to the world; `22` restricted to trusted IPs. Do **not** open 5432, 6379 or 8000.

## 2. Automatic deploys from GitHub (AWS Systems Manager, no SSH)

The deploy job does **not** use SSH, so port 22 can stay restricted to your own IP. GitHub assumes a short-lived AWS role through OpenID Connect (no long-lived AWS keys) and tells the instance, through Systems Manager (SSM), to run `infra/scripts/deploy.sh`.

### One-time AWS setup (console, Singapore region)

1. **Let the instance be managed by SSM.** IAM -> Roles -> your instance role (create one for EC2 if the instance has none: IAM -> Roles -> Create role -> AWS service -> EC2) -> Add permissions -> attach **AmazonSSMManagedInstanceCore**. Then EC2 -> your instance -> Actions -> Security -> Modify IAM role -> select it. After a few minutes the instance appears under Systems Manager -> Fleet Manager (Ubuntu 24.04 AWS images ship the SSM agent).
2. **Create the GitHub identity provider.** IAM -> Identity providers -> Add provider -> OpenID Connect -> Provider URL `https://token.actions.githubusercontent.com`, Audience `sts.amazonaws.com`.
3. **Create the deploy role.** IAM -> Roles -> Create role -> Web identity -> provider `token.actions.githubusercontent.com`, audience `sts.amazonaws.com` -> skip permissions for now -> name it `github-deploy-jobslahfinder`. Then open the role -> Trust relationships -> Edit and use (replace `ACCOUNT_ID`):

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": { "Federated": "arn:aws:iam::ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com" },
    "Action": "sts:AssumeRoleWithWebIdentity",
    "Condition": {
      "StringEquals": {
        "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
        "token.actions.githubusercontent.com:sub": "repo:Ryan-wong123/Jobslahfinder:environment:production"
      }
    }
  }]
}
```

4. **Give the role only what it needs.** Role -> Add permissions -> Create inline policy -> JSON (replace `ACCOUNT_ID` and `INSTANCE_ID`, e.g. `i-0123456789abcdef0`):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "ssm:SendCommand",
      "Resource": [
        "arn:aws:ssm:ap-southeast-1::document/AWS-RunShellScript",
        "arn:aws:ec2:ap-southeast-1:ACCOUNT_ID:instance/INSTANCE_ID"
      ]
    },
    {
      "Effect": "Allow",
      "Action": ["ssm:GetCommandInvocation", "ssm:ListCommandInvocations"],
      "Resource": "*"
    }
  ]
}
```

### GitHub settings

Repository -> Settings -> Secrets and variables -> Actions -> **Secrets**:

| Secret | Value |
| --- | --- |
| `AWS_DEPLOY_ROLE_ARN` | ARN of `github-deploy-jobslahfinder`, e.g. `arn:aws:iam::ACCOUNT_ID:role/github-deploy-jobslahfinder` |
| `EC2_INSTANCE_ID` | The instance ID, e.g. `i-0123456789abcdef0` |
| `DEPLOY_PATH` | `/opt/jobslahfinder` |

Optional **variable** `AWS_REGION` (defaults to `ap-southeast-1`). The old `EC2_HOST`, `EC2_USER`, `EC2_PORT` and `EC2_SSH_KEY` secrets are no longer used and can be deleted.

Repository -> Settings -> Environments -> `production` -> Deployment branches -> **Selected branches: `main`** so only `main` can use the role. (Do this after your first test run if you test from another branch.)

Never commit keys, `.env`, backups, logs or uploaded files.

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

Push to `main` (or run the workflow manually). The deploy job calls `infra/scripts/ssm-deploy.sh`, which runs `infra/scripts/deploy.sh` on the instance through SSM: backup -> checkout -> build -> `alembic upgrade head` -> start -> HTTPS `/health` smoke test -> rollback of the code on failure. Migrations are not reverted on rollback; restore the pre-deploy backup if a schema change must be undone.

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
