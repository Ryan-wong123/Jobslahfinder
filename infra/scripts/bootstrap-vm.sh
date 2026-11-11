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
sudo apt-get install -y git gnupg curl ca-certificates cron openssl unattended-upgrades logrotate apparmor

if ! command -v docker >/dev/null 2>&1; then
  echo "==> Installing Docker"
  sudo install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo tee /etc/apt/keyrings/docker.asc >/dev/null
  sudo chmod a+r /etc/apt/keyrings/docker.asc
  . /etc/os-release
  printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu %s stable\n' "$(dpkg --print-architecture)" "$VERSION_CODENAME" | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
  sudo apt-get update
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
sudo usermod -aG docker "$RUN_USER"
sudo systemctl enable --now docker
sudo bash "$REPO_DIR/infra/scripts/install-sandbox-apparmor.sh"

if ! command -v aws >/dev/null 2>&1; then
  echo "==> Installing AWS CLI"
  sudo snap install aws-cli --classic
fi

echo "==> Creating protected directories"
sudo mkdir -p /var/backups/jobapp
sudo chmod 700 /var/backups/jobapp
sudo install -d -m 700 /etc/jobapp
if ! sudo test -s /etc/jobapp/backup-passphrase; then
  sudo install -m 600 /dev/null /etc/jobapp/backup-passphrase
  openssl rand -base64 48 | sudo tee /etc/jobapp/backup-passphrase >/dev/null
fi
sudo install -m 644 "$REPO_DIR/infra/logrotate/jobslahfinder" /etc/logrotate.d/jobslahfinder
for f in jobapp-backup.log jobapp-cert-renew.log jobapp-monitor.log; do
  sudo touch "/var/log/$f"; sudo chmod 640 "/var/log/$f"
done

echo "==> Enabling automatic security updates"
sudo dpkg-reconfigure -f noninteractive unattended-upgrades || true

echo "==> Installing cron jobs (cert renewal twice daily, backup daily)"
CRON_TMP="$(mktemp)"
sudo crontab -l 2>/dev/null | grep -vE 'infra/scripts/(renew-certs|backup-prod|monitor).sh' > "$CRON_TMP" || true
cat >> "$CRON_TMP" <<CRON
17 3,15 * * * cd $REPO_DIR && sh infra/scripts/renew-certs.sh >> /var/log/jobapp-cert-renew.log 2>&1
30 2 * * * cd $REPO_DIR && bash infra/scripts/backup-prod.sh >> /var/log/jobapp-backup.log 2>&1
*/5 * * * * cd $REPO_DIR && bash infra/scripts/monitor.sh >> /var/log/jobapp-monitor.log 2>&1
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
  4. Follow docs/SECURITY_REMEDIATION.md for migrations and restricted-role provisioning.
  5. docker compose run --rm backend python -m app.cli create-initial-admin --email you@example
  6. Run the release deployment script and verify-deploy.sh; escrow the backup key securely.
MSG
