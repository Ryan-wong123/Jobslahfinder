# Deployment Commands

Use the [production deployment guide](DEPLOYMENT.md) for a new EC2 host and the
[security upgrade runbook](SECURITY_REMEDIATION.md#existing-production-upgrade)
for an existing installation.

## Deploy a release

Merge or push to `main`. To deploy the current `main` on demand, open **Actions**,
select **CI/CD**, and choose **Run workflow** on `main`. Rerunning failed jobs
uses the original commit.

GitHub Actions builds, scans, and publishes the backend, scraper, and frontend
images to GHCR. The EC2 deploy user needs read access to pull the exact digests.
The workflow assumes the AWS deploy role through OIDC and invokes
`infra/scripts/ssm-deploy.sh`. The remote deploy script takes an encrypted backup,
runs migrations with a one-shot administrator connection, provisions database
roles, and verifies the release over HTTPS.

## Inspect production from Systems Manager

Run as the `ubuntu` deploy user:

```bash
cd /opt/jobslahfinder
git log -1 --oneline
docker compose ps
docker compose logs --tail=100 nginx frontend backend
bash infra/scripts/verify-deploy.sh
```

Check the live endpoints from outside the VM:

```bash
curl -fsS https://jobs.jobslahfinder.com/health
curl -fsS https://jobs.jobslahfinder.com/api/ready
```

## Start the installed release after a VM restart

Run as the `ubuntu` deploy user in the deployed checkout. The production
`.env` contains the image references saved by the last successful deployment.

```bash
cd /opt/jobslahfinder
test -s .release.env && docker compose up -d --no-build --wait --wait-timeout 240
```

Use GitHub Actions to apply a new release and its migrations.

## Take an encrypted backup

```bash
cd /opt/jobslahfinder
sudo -n bash infra/scripts/backup-prod.sh
```

See the [backup and monitoring runbook](SECURITY_REMEDIATION.md#backups-and-monitoring)
for restore testing and scheduled checks.
