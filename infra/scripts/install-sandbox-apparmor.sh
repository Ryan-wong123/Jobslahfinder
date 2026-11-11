#!/usr/bin/env bash
# Install only the private parser worker's profile; keep Docker's default intact.
set -Eeuo pipefail
cd "$(dirname "$0")/../.."

if ! docker info --format '{{json .SecurityOptions}}' | grep -q 'name=apparmor'; then
  if [ "${1:-}" = '--require' ]; then
    echo 'This verification requires an AppArmor-enabled Docker host.' >&2
    exit 1
  fi
  echo 'Docker does not advertise AppArmor; no host policy was changed.'
  exit 0
fi

[ "$(id -u)" -eq 0 ] || { echo 'Run this policy installer with sudo.' >&2; exit 1; }
command -v apparmor_parser >/dev/null || { echo 'Install the apparmor package first.' >&2; exit 1; }
install -m 644 infra/security/jobslahfinder-parser.apparmor /etc/apparmor.d/jobslahfinder-parser
apparmor_parser -r -W /etc/apparmor.d/jobslahfinder-parser
echo 'Loaded the jobslahfinder-parser AppArmor profile.'
