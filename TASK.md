# TASK.md - Remaining deployment work (handoff for a local Claude session)

This file lets a new Claude session (running locally, able to use the user's browser/computer) finish the
remaining production-deployment work for **Jobslahfinder**. Read `AGENTS.md` and `docs/DEPLOYMENT.md` first.

## Current state (verified)

- Live site: `https://jobs.jobslahfinder.com` (valid Let's Encrypt certificate, HSTS/CSP present).
- Server: AWS EC2 (Ubuntu 24.04, Singapore `ap-southeast-1`), Elastic IP `18.138.7.111`, repo at `/opt/jobslahfinder`
  on branch `production`, running via `docker-compose.yml` + `docker-compose.prod.yml` (`COMPOSE_FILE` is set in `.env`).
- `infra/scripts/verify-deploy.sh` passes 19/19. Admin login + 2FA, password-reset email (Brevo), scraping, resume
  extraction (Gemini model `gemini-3.5-flash-lite`), recommendations, cover letters, and local backup + restore test all work.
- GitHub: branch `production`, **draft PR #61** into `main` (CI is green). Merging to `main` triggers the deploy job.
- Security group: port 22 is restricted to the user's own IP (`/32`); 80/443 are open to the world. **Keep it that way.**
- Deploys from GitHub use **AWS Systems Manager (SSM) + GitHub OIDC**, not SSH
  (`infra/scripts/ssm-deploy.sh`, `.github/workflows/ci-cd.yml`). The old SSH secrets (`EC2_HOST`, `EC2_USER`,
  `EC2_PORT`, `EC2_SSH_KEY`) are no longer used. Only three secrets are needed (see Phase A).

## Rules for the assistant doing this

- **Do not ask for or type the user's passwords, MFA codes, card details, or API keys.** Have the user sign in
  (AWS console, GitHub) and handle MFA themselves; continue once they are signed in.
- Never paste secret values (keys, `.env` contents, tokens) into chat, files, commits, or logs.
- Ask the user to confirm before: creating/editing IAM roles or policies, changing security group rules,
  saving GitHub secrets, taking PR #61 out of draft, or merging it. **Never merge without explicit confirmation.**
- **Never open port 22 to `0.0.0.0/0`.**
- Commits must be authored only as the user: `git config user.name "ryan wong"` and
  `git config user.email "42606643+Ryan-wong123@users.noreply.github.com"`. Do **not** add Claude as author or
  co-author, and do not add a Claude attribution line.
- Do not commit `.env`, keys, or certificates. Work on branch `production`.
- Tick items in `docs/TASKS.md` only after verifying them.

## Useful facts

| Item | Value |
| --- | --- |
| Repo | `Ryan-wong123/Jobslahfinder` (PR #61, `production` -> `main`) |
| Region | `ap-southeast-1` (Singapore) |
| Domain / IP | `jobs.jobslahfinder.com` / `18.138.7.111` |
| Server path | `/opt/jobslahfinder` (SSH user `ubuntu`) |
| SSH (from the user's PC, PowerShell) | `ssh -i C:\Users\ryan\Documents\jobslahfinder-key2.pem ubuntu@18.138.7.111` (run `icacls` fixes if Windows complains about key permissions) |
| GitHub secrets page | https://github.com/Ryan-wong123/Jobslahfinder/settings/secrets/actions |
| GitHub environments page | https://github.com/Ryan-wong123/Jobslahfinder/settings/environments |
| Workflow run page | https://github.com/Ryan-wong123/Jobslahfinder/actions/workflows/ci-cd.yml |

---

## Phase A - Let GitHub deploy without SSH (AWS Systems Manager + OIDC)

**STATUS: DONE** (verified: workflow run #155 on `production` assumed the AWS role and deployed via SSM successfully).

Goal: merging to `main` deploys automatically while SSH stays closed. About 20 minutes in the AWS console
(region **Asia Pacific (Singapore)**). The user must be signed in to AWS.

### A1. Let the instance accept SSM commands
- [x] AWS console -> EC2 -> select the instance -> **Security** tab -> note the **IAM role** (if none, create one:
      IAM -> Roles -> Create role -> AWS service -> **EC2**, name e.g. `jobapp-ec2-role`).
- [x] IAM -> Roles -> that role -> **Add permissions -> Attach policies** -> attach **AmazonSSMManagedInstanceCore**.
- [x] If the instance had no role: EC2 -> instance -> **Actions -> Security -> Modify IAM role** -> select it -> Update.
- [x] Wait ~5 minutes, then Systems Manager -> **Fleet Manager** must list the instance as **Online**.
      (Ubuntu 24.04 AWS images include the SSM agent. If it stays missing, on the server run
      `sudo snap list amazon-ssm-agent` and `sudo systemctl status snap.amazon-ssm-agent.amazon-ssm-agent`.)
- [x] Record the **instance ID** (`i-...`) and the **AWS account ID** (top-right menu in the console).

### A2. GitHub identity provider (once per AWS account)
- [x] IAM -> **Identity providers** -> Add provider -> **OpenID Connect**.
      Provider URL: `https://token.actions.githubusercontent.com`  Audience: `sts.amazonaws.com`.
      (Skip if it already exists.)

### A3. Deploy role
- [x] IAM -> Roles -> Create role -> **Web identity** -> provider `token.actions.githubusercontent.com`,
      audience `sts.amazonaws.com` -> skip permissions -> name `github-deploy-jobslahfinder` -> create.
- [x] Open the role -> **Trust relationships -> Edit trust policy** and set it to the following
      (replace `ACCOUNT_ID`). The `sub` claim is the **production environment** because the deploy job uses
      `environment: production`:

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
        "token.actions.githubusercontent.com:sub": "repo:Ryan-wong123@42606643/Jobslahfinder@1241196453:environment:production"
      }
    }
  }]
}
```

- [x] Role -> **Add permissions -> Create inline policy -> JSON**, name `ssm-deploy-jobslahfinder`
      (replace `ACCOUNT_ID` and `INSTANCE_ID`):

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

- [x] Copy the role's **ARN** (`arn:aws:iam::ACCOUNT_ID:role/github-deploy-jobslahfinder`).

### A4. GitHub secrets (the user must confirm before saving)
Repository -> Settings -> Secrets and variables -> Actions -> **Secrets** -> New repository secret:

| Secret | Value |
| --- | --- |
| `AWS_DEPLOY_ROLE_ARN` | the role ARN from A3 |
| `EC2_INSTANCE_ID` | the `i-...` instance ID |
| `DEPLOY_PATH` | `/opt/jobslahfinder` |

- [x] All three secrets saved. (Optional repository **variable** `AWS_REGION`; defaults to `ap-southeast-1`.)
- [x] Old secrets `EC2_HOST`, `EC2_USER`, `EC2_PORT`, `EC2_SSH_KEY` deleted (unused); only the three secrets above remain.

> **Note - this repository's OIDC subject claim is customised.** GitHub issues the token subject as
> `repo:Ryan-wong123@42606643/Jobslahfinder@1241196453:environment:production` (owner ID and repo ID included),
> not the default `repo:OWNER/REPO:environment:production`. The trust policy above uses the real value. If the
> deploy fails with `Not authorized to perform sts:AssumeRoleWithWebIdentity`, read the exact `sub` from AWS
> CloudTrail (Event history -> `AssumeRoleWithWebIdentity` -> the "User name" field) and match the trust policy to it.

---

## Phase B - First test deploy (from the `production` branch)

**STATUS: DONE** - run #155 (commit `e7e7dcd`) succeeded, and the server checks below are verified.

- [x] GitHub -> Actions -> **CI/CD** -> **Run workflow** -> branch **`production`** -> Run.
      (The deploy job runs on `workflow_dispatch` and on pushes to `main`.)
      If the `production` environment requires approval, the user approves it.
- [x] Watch the **Deploy To EC2** job. Expected log: `SSM command id: ...`, status lines
      `Pending/InProgress ... Success`, then `Deploy succeeded.`
- [x] On the server: `cd /opt/jobslahfinder && git log -1 --oneline` shows the deployed commit, and
      `bash infra/scripts/verify-deploy.sh` still passes 19/19. (Verified after run #155 and after the merge deploy.)
- [x] The pre-deploy backup was created: `sudo ls -1 /var/backups/jobapp | tail -3`. (Verified.)

### If the deploy job fails

| Symptom | Likely cause / fix |
| --- | --- |
| `Not authorized to perform sts:AssumeRoleWithWebIdentity` | Trust policy `sub` does not match. For this repo it must be exactly `repo:Ryan-wong123@42606643/Jobslahfinder@1241196453:environment:production` (customised claim, see the note in Phase A); check the OIDC provider exists and the audience is `sts.amazonaws.com`. CloudTrail shows the `sub` GitHub actually sent. |
| Status `Failed`, `set: Illegal option -o pipefail` in the remote errors | SSM runs the command lines with `/bin/sh` (dash). Keep those lines POSIX (`set -eu`); bash-only code belongs in the decoded script. Fixed in `ssm-deploy.sh`. |
| `AccessDeniedException ... ssm:SendCommand` | Inline policy has the wrong account ID / instance ID / region in the ARNs. |
| `InvalidInstanceId` | Instance not Online in Fleet Manager: instance role missing `AmazonSSMManagedInstanceCore`, or the SSM agent is not running. |
| Status `Failed`, output shows `Permission denied` on `/var/backups/jobapp` | Should not happen (deploy.sh uses sudo). Check that `ubuntu` has passwordless sudo: `sudo -n true`. |
| Status `Failed`, smoke test failed, "Rolling back" in output | The new commit broke `/health`. deploy.sh rolled the code back. Read the output, fix the code, redeploy. Migrations are NOT reverted. |
| Job cancelled while running | Deploy command still finishes on the server; check `docker compose ps` and rerun if needed. |

---

## Phase C - Lock it down and merge

- [x] (Done) GitHub -> Settings -> **Environments** -> `production` -> Deployment branches and tags ->
      **Selected branches: `main`** (so only `main` can assume the AWS role). Do this **after** the Phase B test,
      because the test runs from the `production` branch.
- [ ] (Optional) Environments -> `production` -> Required reviewers: add the user for a manual approval step.
- [ ] (Optional) Settings -> Branches -> protect `main`: require pull request and passing checks.
- [x] **With the user's explicit confirmation:** take PR #61 out of draft and merge it. The merge triggers
      the first automatic deploy to production. (Done: merged as `cb23dd1`, run #156 on `main` succeeded.)
- [x] After the merge deploy finishes: run `bash infra/scripts/verify-deploy.sh` on the server (must be 19/19). (19/19.)

---

## Phase D - Remaining verification (small)

- [x] **External port scan** (done: 5432, 6379, 8000 reported `filtered` on 18.138.7.111 from an external tool;
      SSH rule limited to the user's own IP, 80/443 public).
- [x] Observe the first scheduled backup (cron 02:30 UTC): `sudo ls -lt /var/backups/jobapp | head` the next day,
      and `sudo tail /var/log/jobapp-backup.log`. (Verified: the 2026-11-07 02:30 UTC run logged "Backup complete".)
- [ ] Observe the weekly scraping run (Sundays 18:00 UTC) in `/admin` -> scraping runs. (Not yet observable.)
- [x] Certificate renewal cron exists (`sudo crontab -l`); optionally dry run:
      `cd /opt/jobslahfinder && docker compose run --rm certbot renew --dry-run`. (Cron at 03:17 and 15:17 UTC; dry run succeeded.)
- [x] Update `docs/TASKS.md` (tick what was verified), commit as the user, push to `production`.

Already verified by the user: a normal (non-admin) account cannot use `/admin`; unknown API paths return a
generic `{"detail":"Not Found"}` with no stack trace.

## Phase E - Optional / later

- [ ] **Off-server backups (S3).** The bucket `jobslahfinderapp-backup-upload` does **not** exist (S3 returned
      404). To enable: create the bucket in Singapore (Block all public access ON, versioning ON); grant the
      instance role `s3:PutObject` on `arn:aws:s3:::BUCKET/jobapp/*` and `s3:ListBucket` on the bucket with prefix
      `jobapp/*`; then on the server uncomment/set `BACKUP_S3_URI=s3://BUCKET/jobapp` in `.env`, run
      `sudo bash infra/scripts/backup-prod.sh`, and check `aws s3 ls s3://BUCKET/jobapp/`.
      (Currently `BACKUP_S3_URI` is commented out; backups are kept locally for 14 days.)
- [ ] Add the risk-engine API key to a password manager only if the machine API is needed
      (`curl -X POST https://jobs.jobslahfinder.com/risk-engine/setup`, shown once). The risk dashboard itself uses
      the normal admin login: `https://jobs.jobslahfinder.com/risk-engine/admin/dashboard`.
- [ ] Nonce-based CSP to remove `'unsafe-inline'` for scripts (needs Next.js middleware + browser testing).
- [ ] Squash the duplicate-numbered Alembic migrations (test against a fresh DB and an upgrade).
- [ ] Per-user Gemini quotas, scraper-failure alerts, "last updated" notice for scraped jobs.

## Operational notes

- Gemini model names get retired. If resume extraction suddenly fails (`parser_failed`) and the worker log shows
  `404 Not Found` from `generativelanguage.googleapis.com`, test model names with `curl` against
  `/v1/models/<name>:generateContent` and update `GEMINI_RESUME_MODEL` / `GEMINI_COVER_LETTER_MODEL` in the
  server `.env`, then `docker compose up -d backend worker`.
- If the user's home IP changes, SSH stops working: edit the security group's SSH rule to **My IP** again.
- Manual deploy fallback on the server: `cd /opt/jobslahfinder && DEPLOY_SHA=$(git rev-parse origin/production) bash infra/scripts/deploy.sh`.
- Do not re-run the `.env` secret-generation block once the database volume exists (it would change the Postgres
  password and lock the app out of its data).
