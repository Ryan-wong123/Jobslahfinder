# Security remediation — 10 November 2026

This change implements the security and deployment review in the repository.
Local tests use synthetic credentials and disposable containers. They do not
modify the deployed AWS VM, IAM policies, registry permissions, DNS, or production data.

## Application controls

- SQLAlchemy hides SQL parameters and uses bounded connection/pool timeouts.
- Application, Uvicorn, and Celery logging filters suppress arbitrary exception
  values and tracebacks, including exceptions passed as formatting arguments.
- Risk-engine HTTP initialization returns 404. Production does not expose its
  machine APIs or documentation. Initialize state with the operator CLI:
  `docker compose run --rm backend python -m app.cli initialize-risk-engine`.
  This exclusively creates mode-0600 state and never prints the API credential.
- Nginx repeats the complete header policy in every location that declares
  `add_header`, including API and error responses. Access logs omit query strings,
  Referer, cookies, and request bodies. Multipart overhead is allowed while the
  backend still enforces a strict 5 MiB resume-file limit.
- Redis-backed atomic limits have expiring, HMAC-derived keys and fail closed
  when unavailable. Limits apply to IPs and authenticated users; login/reset also
  have account limits, and generation has a shared daily per-user budget.
- Unknown-account and locked-account login paths perform dummy password hashing
  verification. Lockout uses the same credential error as other failures.
- Password resets atomically consume a token while holding the account lock,
  invalidate all outstanding reset tokens, and revoke sessions. SMTP delivery is
  outside request handling through a transactional encrypted outbox. Outbox
  retries are bounded, expire, audit delivery status, and erase delivered/failed
  payloads. Tokens are never placed in plaintext broker messages.
- Email changes require the current password, a TOTP code, and a single-use
  verification link sent to the new address. The old address receives notices.
  Confirmation requires the account session and revokes every session and reset
  token. `PATCH /me` cannot bypass this workflow. Verification/reset links put
  tokens in URL fragments so tokens are not sent in HTTP URLs.
- Resume storage has per-user count/byte quotas, serialized against concurrent
  uploads. Parsing runs in a disposable process with a parent-enforced timeout,
  Linux memory/CPU limits, bounded input/output, and synthetic bootstrap settings.
  Linux production adds a Bubblewrap filesystem/PID/network sandbox, exposing
  only read-only code/libraries and the single document on stdin. Parent process
  environments and uploaded volumes are hidden.
  `/proc` stays empty, preserving Docker system-path masks without exposing
  inherited process information. The parser receives no real database,
  session, SMTP, or AI credentials. Gemini calls
  use transport timeouts rather than unkillable timeout threads.

## Service isolation

Production uses separate frontend, ingress, data, scrape, and outbound networks.
The database/data networks are internal and no database, Redis, API, upload, or
backup ports are published.

The API uses `jobapp_runtime`, the private worker `jobapp_worker`, and the scraper
`jobapp_scraper`. The private worker cannot read authentication tables, TOTP
enrollments, or password-reset tokens and receives no authentication signing keys.
An independent `DATA_ENCRYPTION_SECRET` protects outbox mail. Existing and new TOTP
enrollments retain the API-only key and format, preserving rollback compatibility;
private workers cannot decrypt TOTP state even with their outbox encryption key.
The runtime role cannot create database objects or update/delete audit records.
The scraper can read source configuration and insert/update normalized jobs and
scraping runs, and append audits. It cannot read users, resumes, sessions,
recovery tokens, or encrypted mail. Administrator credentials are confined to
the PostgreSQL service and one-shot operator migration/backup operations.

The API refuses production startup with a privileged database role. Run
`bash infra/scripts/provision-db-roles.sh` after every migration to apply grants
to new tables. It supports existing database volumes; changing `POSTGRES_USER`
does not change an existing database role and is not the migration procedure.

Redis has separate `auth` and `broker` ACL users. Key patterns and command
allowlists prevent broker clients from reading authentication/rate-limit keys,
including after switching Redis database numbers. Redis administration is denied
to both clients. Only the API receives `AUTH_REDIS_URL`.

Scraping runs on the `scraping` queue in a separate browser image. API-triggered
runs are stored as PENDING records and claimed by the worker. Browser tooling is
absent from the API/private-worker image; the scraper has no resume mount, SMTP
credentials, authentication keys, or AI key. It has a restricted outbound HTTPS
proxy which rejects private/metadata addresses and unapproved domains. Review
required CDN domains in `infra/squid/squid.conf` when portals change.

The scraper retains Chromium's native sandbox with the documented Docker
seccomp profile in `infra/security/`. All application services drop capabilities,
use `no-new-privileges`, have bounded CPU/memory/PIDs, and use read-only root
filesystems with explicit temporary storage. The private worker mounts resumes
read-only. Do not fix a failing browser probe by adding SYS_ADMIN or disabling
the browser sandbox. Test the profile on the target AWS kernel before release.

## Existing-production upgrade

1. Keep the existing PostgreSQL volume and administrator credentials. Before
   changing configuration, preserve a protected backup and escrow its decryption
   key outside the VM. Never delete the volume to change database roles.
2. Review `.env.example`, then run `configure-env.sh` with the existing domain and
   certificate email. It preserves existing secrets, keeps the old administrator
   DSN as `MIGRATION_DATABASE_URL`, and generates independent runtime/scraper and
   Redis credentials. Never print the resulting `.env`.
3. Run `bootstrap-vm.sh` to install the protected backup-key file, log rotation,
   and monitoring cron if those are not already provisioned. Securely escrow the
   key; generating a replacement does not decrypt old backups.
   The bootstrap also loads the parser's scoped AppArmor policy. On an existing
   prepared VM, run `sudo bash infra/scripts/install-sandbox-apparmor.sh` before
   starting the upgraded worker; see `infra/security/README.md`.
   Release deployment reloads that same policy before replacing services and
   fails early if the host lacks AppArmor support or its policy loader.
4. Configure read access to the GHCR release packages for the deploy user, or
   deliberately make the packages public. CI publishes scanned images using its
   short-lived GitHub token. A VM credential, if needed, must have read-packages
   scope only, live outside the repository, and be passed via `--password-stdin`.
5. Deploy the CI-produced `BACKEND_IMAGE`, `SCRAPER_IMAGE`, and `FRONTEND_IMAGE`
   digest references through SSM. The deploy script pulls those exact images,
   takes an encrypted pre-migration backup, applies migrations in an ephemeral
   administrator process, provisions restricted roles, waits for health, and
   runs the HTTPS verification gate. It does not rebuild release images on EC2.
6. Verify the authenticated workflows and the new email-change verification with
   the real SMTP provider. The old email remains active until verification.

The release script retains previous image references and rolls application images
back between releases with the same `security-v1` service contract, retaining the
audited infrastructure configuration. The first upgrade from legacy deployment
has no compatible rollback baseline: failure stops application writers and
requires a roll-forward or restoration of the pre-upgrade backup/configuration.
Database migrations are additive and are not automatically downgraded. Bump the
contract marker for future incompatible service changes rather than silently
attempting an unsafe rollback.
Successful image references are persisted in `.env` and ignored release manifests,
so an ordinary service restart does not silently select old local build tags.

## Backups and monitoring

Production backups require `BACKUP_PASSPHRASE_FILE`; plaintext backups are not an
optional production mode. The script briefly stops writers for a coherent
database/file snapshot and always restarts the services that were running. Risk
SQLite databases are copied with SQLite's backup API. Artifacts are encrypted
with GPG/AES256, checksummed, permission-restricted, and optionally uploaded to
S3 with server-side encryption. Configure bucket access, versioning, retention,
and the VM instance role separately. Include an independent copy/escrow of the
application encryption keys needed to decrypt TOTP/outbox data; never put `.env`
inside a publicly accessible backup.

- Database restore drill: `bash infra/scripts/restore-test.sh <backup-directory>`.
- Full maintenance restore: `CONFIRM_RESTORE=restore-jobapp bash infra/scripts/restore-prod.sh <backup-directory>`.
  This takes a recovery point, stops writers, transactionally restores PostgreSQL,
  restores both protected volumes, reapplies grants, and verifies service health.
- Monitoring: `monitor.sh` checks readiness, every service, certificate expiry,
  and daily-backup freshness. `MONITOR_CLOUDWATCH=1` publishes only a bounded
  health metric. Apply `infra/monitoring/alarms.yml` with an existing subscribed
  SNS topic and grant the VM only the necessary metric-publication permission.
  Missing heartbeat data also alarms. No notifications or IAM changes are made
  merely by editing these files.

## Verification and maintenance

Local verification on 10 November 2026:

- 291 backend/risk-engine tests passed; combined coverage 73.44%, excluding tests.
- Frontend type checking/lint, 17 frontend regression tests, production build,
  and three Chromium browser tests passed. The browser visited every app route.
- An isolated production-profile deployment passed the HTTPS workflow checks, including
  MFA, denied admin access, malicious-input handling, a real DOCX upload through
  Redis to the private sandboxed worker, encrypted verification mail, email
  confirmation, and session revocation. No message was sent to a real recipient.
- Real PostgreSQL migration/least-privilege/concurrent-reset/encrypted-restore,
  Redis ACL/full Celery startup, parser isolation, native Chromium sandbox,
  effective Nginx headers, and all four release/rollback decision tests passed.
- Python and npm dependency audits, the high-severity Bandit gate, clean-source
  Trivy vulnerability/secret/configuration scan, Compose validation, and shell
  syntax checks passed. Medium static-analysis findings remain for contextual
  review; the high-severity gate is not a claim of zero scanner findings.
- All three built release images passed Trivy with no fixable high or critical
  vulnerabilities. npm's build tooling is absent from the production frontend.
- Scheduler health uses a separate mode-0600 heartbeat updated after successful
  task publication, rather than depending on buffered schedule-database metadata.

Target-VM rollout, real SMTP delivery, AWS IAM/S3 configuration, registry access,
backup-key escrow, alarm subscriptions, and target-kernel sandbox behavior
remain operator deployment checks. They have not been represented as completed
by local tests. Registration email verification and a nonce-based CSP remain
separate hardening items; the existing CSP limitation is documented below.

The Linux CI compatibility repair was verified in
[GitHub Actions run 42829760254](https://github.com/Ryan-wong123/Jobslahfinder/actions/runs/42829760254):
backend, frontend, migrations, security, and container verification/scanning all
passed. The parser profile was loaded and confirmed in enforce mode on the
runner; empty-procfs isolation and real DOCX extraction passed alongside the
native Chromium sandbox. EC2 deployment was intentionally skipped for this pull
request. The CI fix also supplies the image digests required by SSM deployment
and loads the worker policy during deployment preflight.

Use `infra/scripts/test-backend.py` with the locked test environment. Coverage
excludes tests themselves and CI enforces 70%. The additional infrastructure
tests exercise real Nginx responses, PostgreSQL privileges/concurrent resets/
encrypted restores, Redis ACLs/Celery, and Chromium sandbox startup.

Runtime, scraper, test, and scanner Python lockfiles contain hashes. Docker base
images and GitHub actions are pinned to verified digests/revisions. Signed OS
security updates are applied during the build; CI scans the final backend,
frontend, and scraper images before publishing them. Gitleaks scans complete
history; exact documented non-production password-fixture fingerprints are the
only new exclusions. Dependabot checks dependencies and action/base-image updates
weekly. When Python dependencies change, regenerate all three backend lockfiles
with Python 3.12 and rerun the image scans; do not edit generated hashes manually.

Kubernetes remains outside this single-VM Compose architecture. Moving to it
requires a separate design for persistent resume/risk state, database/Redis access,
network policies, secrets, probes, resource budgets, and restore procedures.
Installing it would not resolve any remaining host/account configuration work.

The existing inline-script CSP allowance is retained for Next.js hydration and
the server-rendered risk dashboard. Content remains escaped/sanitized, and no
untrusted HTML sink was introduced. Migrating those pages to request nonces is
a separate compatible-rendering change, not a reason to disable CSP.
