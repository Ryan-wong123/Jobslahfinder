#!/usr/bin/env bash
# One-time setup of a fresh Ubuntu 22.04/24.04 VM for the production stack.
# Run as a normal sudo-capable user (e.g. ubuntu) from the repository checkout:
#   bash infra/scripts/bootstrap-vm.sh
# Idempotent: safe to re-run.
set -Eeuo pipefail

REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
RUN_USER="${SUDO_USER:-$USER}"

echo "==> Updating packages"
sudo apt-get update -y
sudo apt-get upgrade -y
sudo apt-get install -y git gnupg curl ca-certificates cron openssl unattended-upgrades

if ! command -v docker >/dev/null 2>&1; then
  echo "==> Installing Docker"
  curl -fsSL https://get.docker.com | sudo sh
fi
sudo usermod -aG docker "$RUN_USER"
sudo systemctl enable --now docker

if ! command -v aws >/dev/null 2>&1; then
  echo "==> Installing AWS CLI"
  sudo snap install aws-cli --classic
fi

echo "==> Creating protected directories"
sudo mkdir -p /var/backups/jobapp
sudo chmod 700 /var/backups/jobapp
for f in jobapp-backup.log jobapp-cert-renew.log; do
  sudo touch "/var/log/$f"; sudo chmod 640 "/var/log/$f"
done

echo "==> Enabling automatic security updates"
sudo dpkg-reconfigure -f noninteractive unattended-upgrades || true

echo "==> Installing cron jobs (cert renewal twice daily, backup daily)"
CRON_TMP="$(mktemp)"
sudo crontab -l 2>/dev/null | grep -v 'jobapp-' > "$CRON_TMP" || true
cat >> "$CRON_TMP" <<CRON
17 3,15 * * * cd $REPO_DIR && sh infra/scripts/renew-certs.sh >> /var/log/jobapp-cert-renew.log 2>&1
30 2 * * * cd $REPO_DIR && bash infra/scripts/backup-prod.sh >> /var/log/jobapp-backup.log 2>&1
CRON
sudo crontab "$CRON_TMP"
rm -f "$CRON_TMP"

if [ ! -f "$REPO_DIR/.env" ]; then
  cp "$REPO_DIR/.env.example" "$REPO_DIR/.env"
  chmod 600 "$REPO_DIR/.env"
  echo "==> Created .env from .env.example. EDIT IT before continuing: nano $REPO_DIR/.env"
fi

cat <<MSG

Bootstrap complete. Next:
  1. Log out and back in (docker group), then: cd $REPO_DIR
  2. Edit .env (DOMAIN, FRONTEND_BASE_URL, secrets, SMTP, GEMINI_API_KEY, BACKUP_S3_URI)
  3. sh infra/scripts/init-letsencrypt.sh
  4. docker compose run --rm backend alembic upgrade head
  5. docker compose run --rm backend python -m app.cli create-initial-admin --email you@example
  6. docker compose up -d && bash infra/scripts/verify-deploy.sh
MSG
