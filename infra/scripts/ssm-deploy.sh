#!/usr/bin/env bash
# Deploy a commit to the EC2 host through AWS Systems Manager (no SSH, no open port 22).
# Runs in GitHub Actions after aws-actions/configure-aws-credentials (OIDC).
#
# Required env: INSTANCE_ID, DEPLOY_PATH, DEPLOY_SHA, AWS_REGION
# Optional env: REMOTE_USER (default ubuntu), DEPLOY_WAIT_SECONDS (default 2400)
set -Eeuo pipefail

: "${INSTANCE_ID:?INSTANCE_ID is required}"
: "${DEPLOY_PATH:?DEPLOY_PATH is required}"
: "${DEPLOY_SHA:?DEPLOY_SHA is required}"
: "${AWS_REGION:?AWS_REGION is required}"
REMOTE_USER="${REMOTE_USER:-ubuntu}"
WAIT_SECONDS="${DEPLOY_WAIT_SECONDS:-2400}"

# Validate everything that is interpolated into the remote script.
[[ "$DEPLOY_SHA" =~ ^[0-9a-f]{40}$ ]] || { echo "DEPLOY_SHA must be a 40-char commit hash." >&2; exit 1; }
[[ "$INSTANCE_ID" =~ ^i-[0-9a-f]{8,17}$ ]] || { echo "INSTANCE_ID looks invalid." >&2; exit 1; }
[[ "$DEPLOY_PATH" =~ ^/[A-Za-z0-9._/-]+$ ]] || { echo "DEPLOY_PATH must be a simple absolute path." >&2; exit 1; }
[[ "$REMOTE_USER" =~ ^[a-z_][a-z0-9_-]*$ ]] || { echo "REMOTE_USER looks invalid." >&2; exit 1; }

REMOTE_SCRIPT=$(cat <<REMOTE
set -Eeuo pipefail
cd "$DEPLOY_PATH"
[ -f .env ] || { echo "Missing $DEPLOY_PATH/.env on the server." >&2; exit 1; }
PREVIOUS_SHA="\$(git rev-parse HEAD)"
git fetch --prune origin
git checkout --force "$DEPLOY_SHA"
# Pre-deploy backup, build, migrate, HTTPS smoke test and automatic code rollback.
PREVIOUS_SHA="\$PREVIOUS_SHA" DEPLOY_SHA="$DEPLOY_SHA" bash infra/scripts/deploy.sh
REMOTE
)

B64="$(printf '%s\n' "$REMOTE_SCRIPT" | base64 -w0)"
PARAMS_FILE="$(mktemp)"
trap 'rm -f "$PARAMS_FILE"' EXIT

# SSM runs these lines with /bin/sh (dash on Ubuntu): keep them POSIX (no pipefail). The real work runs
# under bash in the decoded script. Drop to the deploy user so repo files keep the right owner.
jq -n --arg b64 "$B64" --arg user "$REMOTE_USER" '{
  commands: [
    "set -eu",
    "trap '"'"'rm -f /tmp/jobslah-deploy.sh'"'"' EXIT",
    ("echo " + $b64 + " | base64 -d > /tmp/jobslah-deploy.sh"),
    "chmod 755 /tmp/jobslah-deploy.sh",
    ("sudo -u " + $user + " -H bash /tmp/jobslah-deploy.sh </dev/null")
  ],
  executionTimeout: ["3000"]
}' > "$PARAMS_FILE"

echo "Sending deploy command for $DEPLOY_SHA to $INSTANCE_ID via SSM..."
COMMAND_ID="$(aws ssm send-command \
  --region "$AWS_REGION" \
  --instance-ids "$INSTANCE_ID" \
  --document-name "AWS-RunShellScript" \
  --comment "Deploy ${DEPLOY_SHA:0:12}" \
  --parameters "file://$PARAMS_FILE" \
  --query "Command.CommandId" --output text)"
echo "SSM command id: $COMMAND_ID"

status="Pending"
elapsed=0
while [ "$elapsed" -lt "$WAIT_SECONDS" ]; do
  sleep 15
  elapsed=$((elapsed + 15))
  status="$(aws ssm get-command-invocation --region "$AWS_REGION" \
    --command-id "$COMMAND_ID" --instance-id "$INSTANCE_ID" \
    --query Status --output text 2>/dev/null || echo Pending)"
  echo "[$elapsed s] status: $status"
  case "$status" in
    Success|Failed|Cancelled|TimedOut|Cancelling) break ;;
  esac
done

echo "----- remote output (last part) -----"
aws ssm get-command-invocation --region "$AWS_REGION" \
  --command-id "$COMMAND_ID" --instance-id "$INSTANCE_ID" \
  --query "StandardOutputContent" --output text || true
echo "----- remote errors (last part) -----"
aws ssm get-command-invocation --region "$AWS_REGION" \
  --command-id "$COMMAND_ID" --instance-id "$INSTANCE_ID" \
  --query "StandardErrorContent" --output text || true

if [ "$status" != "Success" ]; then
  echo "Deploy did not succeed (status: $status)." >&2
  exit 1
fi
echo "Deploy succeeded."
