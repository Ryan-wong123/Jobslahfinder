# Secure AI-Assisted Job Aggregation and Application Support Platform

This project is a secure job aggregation and application support platform. It uses a Next.js frontend, FastAPI backend, PostgreSQL database, Redis queue/cache, worker processes, and Nginx reverse proxy.

## What The Website Can Do

The website supports two main roles: job seekers and administrators. The backend enforces authentication, ownership checks, admin RBAC, validation, safe errors, and audit logging for protected workflows.

### Job Seeker Features

Authenticated users can:

- Register, log in, log out, reset passwords, change passwords, and manage their own account.
- View and update their own profile.
- Delete their own account after re-authentication.
- Browse job postings from approved Singapore job sources.
- Search and filter jobs by keyword, company, location, category, and source.
- View job details with sanitized descriptions and an external-link warning.
- Save and unsave jobs for later review.
- Upload PDF or DOCX resumes with extension, declared MIME, content-derived type/signature, size, DOCX archive safety, and path traversal validation.
- View uploaded resume metadata and extraction status.
- Review and edit structured extracted profile data such as skills, education, experience, and years of experience.
- Generate ranked job recommendations from their own extracted profile and active job postings.
- Generate editable cover letter drafts for selected jobs.
- Edit saved cover letter drafts.
- View application preparation history for saved jobs, recommendation refreshes, and cover letter activity.

Normal users cannot:

- Access another user's profile, resumes, saved jobs, recommendations, cover letters, or application history.
- Access admin pages or admin APIs.
- Submit generated cover letters automatically to external job platforms.
- See password hashes, session tokens, reset tokens, raw resume storage paths, or internal errors.

### Administrator Features

Administrators can use `/admin` to:

- View safe platform health status for the backend, database, Redis, and worker.
- View users with safe fields only: ID, email, role, active status, created date, and last login.
- Open a user detail page with safe activity counts only, not resume contents or cover letter text.
- Activate or deactivate users, with safeguards against deactivating their own account or locking out the last active admin.
- Review job summaries, including active/disabled and suspicious/reviewed status.
- Enable or disable job postings.
- Mark or clear suspicious job flags.
- Prepare approved job sources.
- Trigger scraping runs for approved sources.
- View scraping run lists and scraping run detail pages with safe status/count/error fields.
- View audit log metadata.
- Filter audit logs by event type, outcome, user ID, and date range.

Administrators cannot:

- Impersonate users.
- Reset user passwords to a known value.
- View password hashes, session token hashes, reset token hashes, full resume contents, raw extracted resume text, full cover letter text, full AI prompts, API keys, secrets, or stack traces through admin APIs.
- Bypass audit logging for admin modifications.

### Authentication Risk Engine

The authentication risk engine is integrated into the main application login flow. `/auth/login` evaluates the real login context through the risk engine before creating a full user session.

Login decisions work as follows:

- `block` - the login is rejected with a safe generic error or rate-limit message.
- `challenge` - users who already enabled two-factor authentication must complete the TOTP verification flow before a session is created.
- `allow` - users with confirmed two-factor authentication receive a normal session.

New users receive a limited setup session after their first successful password login. That session can only access two-factor setup, two-factor confirmation, and logout until setup is complete. The two-factor flow uses Microsoft Authenticator-compatible TOTP codes.

Trusted device cookies are issued and learned only after successful two-factor setup or successful two-factor verification. Password-only setup login does not mark a device as trusted. Pending two-factor login challenges are stored in Redis with a short TTL and are consumed after successful verification to prevent replay.

The risk engine has its own separate admin surface at `/risk-engine/admin`. This is intentionally separate from the resume analysis platform admin dashboard at `/admin`.

Initialize the risk engine once per environment:

```powershell
Invoke-RestMethod -Method Post http://localhost:8080/risk-engine/setup
```

Store the returned API key in a protected deployment secret or password manager. Do not commit it. Use that key to sign in to `/risk-engine/admin/login`.

The risk engine configuration page allows for configuration of device, IP-prefix, impossible-travel, missing-user-agent, rate-limit, baseline-size, and decision-threshold settings.

### Main Pages

- `/` - home hub
- `/register` - create account
- `/login` - sign in
- `/forgot-password` and `/reset-password` - password reset flow
- `/account` - account and profile management
- `/jobs` - job search and browsing
- `/jobs/[jobId]` - job detail and cover letter generation entry point
- `/saved-jobs` - saved jobs
- `/resumes` - resume upload and resume list
- `/resumes/[resumeId]` - resume metadata and extraction status
- `/resumes/[resumeId]/profile` - extracted profile review
- `/resumes/[resumeId]/profile/edit` - extracted profile editing
- `/recommendations` - ranked job recommendations
- `/cover-letters` - cover letter drafts
- `/cover-letters/[coverLetterId]` - cover letter editor
- `/application-history` - application preparation history
- `/admin` - admin dashboard
- `/admin/users/[userId]` - safe admin user detail
- `/admin/scraping-runs/[runId]` - safe scraping run detail
- `/risk-engine/admin` - separate risk engine dashboard for login risk events and scoring configuration

## Prerequisites

Install Docker Desktop before running the project:

- Docker Desktop for Windows: https://docs.docker.com/installation/windows/

Docker Desktop includes Docker Compose. You do not need to install PostgreSQL or Redis separately because they run inside Docker containers.

Check Docker is available:

```powershell
docker --version
docker compose version
```

## Start The Project

Start and show logs in the terminal:

```powershell
docker compose up --build
```

Or start in the background:

```powershell
docker compose up --build -d
```

Open the app:

```text
http://localhost:8080
```

Backend health check:

```text
http://localhost:8080/health
```

Authenticated user check after login:

```text
http://localhost:8080/api/me
```

Admin RBAC check:

```text
http://localhost:8080/api/admin/health
```

## Local HTTPS With Self-Signed Certificate

Use this to test TLS termination in the Dockerized Nginx reverse proxy on your local Windows machine. The browser will show a certificate warning because the certificate is self-signed.

Create the local certificate:

```powershell
powershell -ExecutionPolicy Bypass -File .\infra\scripts\create-local-cert.ps1
```

Start the app with the local TLS override:

```powershell
docker compose -f docker-compose.yml -f docker-compose.local-tls.yml up -d --build
```

Open:

```text
https://localhost
```

Verify through Nginx:

```powershell
curl.exe -k -I https://localhost
curl.exe -k -I https://localhost/health
curl.exe -k -I https://localhost/api/me
```

Expected results:

- `/` returns `200`.
- `/health` returns `200`.
- `/api/me` returns `401` when you are not logged in, which means Nginx reached the backend.

## Resume Extraction

Resume skill, education, and experience extraction uses Gemini suggestions plus deterministic backend verification. Raw Gemini output is never stored directly: suggested skills must match the local JSON skill taxonomy in `backend/app/data/skills.json` or its aliases and be grounded in the uploaded resume text before they are saved.

```text
RESUME_EXTRACTION_PROVIDER=gemini
GEMINI_RESUME_MODEL=gemini-2.5-flash-lite
GEMINI_API_KEY=replace-with-your-google-ai-api-key
```

For offline development or tests, set `RESUME_EXTRACTION_PROVIDER=local` to use the built-in deterministic parser only. The user can still review and edit extracted fields before recommendations or cover-letter generation use them.

## Cover Letter Generation

Cover letter drafts use Gemini by default when `GEMINI_API_KEY` is configured:

```text
COVER_LETTER_GENERATION_PROVIDER=gemini
GEMINI_COVER_LETTER_MODEL=gemini-2.5-flash-lite
GEMINI_COVER_LETTER_MAX_OUTPUT_TOKENS=2048
```

The backend sends only bounded structured extraction fields and bounded job fields to Gemini. It does not send full raw resume text, log prompts, log generated drafts, or submit anything externally. If Gemini is unavailable, the backend safely falls back to the deterministic draft generator.

## Worker Queue Safety

Background work uses Celery with Redis for resume extraction and scheduled scraping. The worker has task time limits, fair scheduling, late acknowledgements, and a small concurrency setting for the coursework VM.

Resume extraction enqueueing also checks the Celery queue length before adding new extraction tasks. Configure this limit with:

```text
CELERY_QUEUE_MAX_LENGTH=1000
CELERY_RESULT_EXPIRES_SECONDS=3600
```

## Database Setup

After the containers are running, apply database migrations:

```powershell
docker compose run --rm backend alembic upgrade head
```

## Initial Admin Account

Create the first administrator only after migrations have been applied:

```powershell
docker compose run --rm backend python -m app.cli create-initial-admin --email admin@example.com
```

The command prompts for the password twice. Do not pass the admin password on the command line, commit it to `.env`, or store it in documentation. The backend validates the password strength, stores only an Argon2id password hash, creates an audit log entry, and refuses to create another initial admin after an admin already exists.

Login with:

- Email / username: `admin@example.com`
- Password: the password you entered twice when running the command

There is no default admin password. If you forget the password in a local development database, reset the Docker database volume and recreate the initial admin, or use the password reset flow if configured.

## Check Running Services

Show container status:

```powershell
docker compose ps
```

Show logs for all services:

```powershell
docker compose logs
```

Show logs for one service:

```powershell
docker compose logs backend
docker compose logs frontend
docker compose logs worker
docker compose logs beat
```

## Stop The Project

Stop containers but keep database/upload volumes:

```powershell
docker compose down
```

Stop and remove volumes, including local PostgreSQL data:

```powershell
docker compose down -v
```

Only use `docker compose down -v` when you are okay deleting the local database data.

## Commands By Change Scenario

Use this section when deciding what to run after changing code. Run commands from the repository root unless a section says otherwise:


### First Setup Or Fresh Database

Use this after cloning the project, after `docker compose down -v`, or whenever the database volume has been deleted.

```powershell
docker compose up -d --build
docker compose run --rm backend alembic upgrade head
docker compose ps
```

Create the first admin after migrations:

```powershell
docker compose run --rm backend python -m app.cli create-initial-admin --email admin@example.com
```

This creates an admin login for `admin@example.com`. The password is not generated by the command; it is the password you type twice when prompted.

### Backend Python Code Only

Use this for changes under `backend/app/` that do not add dependencies or migrations.

```powershell
docker compose build backend worker beat
docker compose up -d backend worker beat nginx
docker compose logs --tail=80 backend
```

Run backend tests:

```powershell
$env:PYTHONPATH='C:\Users\Downloads\SSD-project\backend\.test-deps;C:\Users\Downloads\SSD-project\backend'
& 'C:\Users\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest
```

### Backend API Or Model Change With Migration

Use this when SQLAlchemy models or Alembic migrations changed.

```powershell
docker compose build backend worker beat
docker compose run --rm backend alembic upgrade head
docker compose up -d backend worker beat nginx
docker compose run --rm backend alembic current
```

### Worker Or Scheduled Task Change

Use this for resume extraction, scraping, Celery task, or beat schedule changes.

```powershell
docker compose build worker beat
docker compose up -d worker beat nginx
docker compose logs --tail=120 worker
docker compose logs --tail=120 beat
```

### Frontend Code Only

Use this for changes under `frontend/src/`.

```powershell
cd frontend
npm run lint
npm run build
cd ..
docker compose build frontend nginx
docker compose up -d frontend nginx
```

### Frontend Dependency Or Dockerfile Change

Use this when `frontend/package.json`, `package-lock.json`, or `frontend/Dockerfile` changed.

```powershell
docker compose build frontend nginx
docker compose up -d frontend nginx
```

### Backend Dependency Or Dockerfile Change

Use this when `backend/pyproject.toml` or `backend/Dockerfile` changed.

```powershell
docker compose build backend worker beat
docker compose up -d backend worker beat nginx
docker compose up -d --build backend worker beat frontend nginx
```

### Nginx Or Docker Compose Change

Use this when `docker-compose.yml` or files under `infra/nginx/` changed.

```powershell
docker compose up -d --build nginx frontend backend worker beat
docker compose ps
```

### Full Rebuild Without Deleting Data

Use this when several services changed but you want to keep local PostgreSQL data and uploaded files.

```powershell
docker compose up -d --build
docker compose ps
```

### Full Reset And Rebuild

This deletes local PostgreSQL, Redis, and uploaded resume volumes. Use only when you are okay losing local data.

```powershell
docker compose down -v
docker compose up -d --build
docker compose run --rm backend alembic upgrade head
```

### Verify Running App

```powershell
docker compose ps
docker compose logs --tail=80 backend
docker compose run --rm backend alembic current
```

Open:

```text
http://localhost:8080
```

## Backup And Restore

Phase 12 adds practical backup/restore scripts under `infra/scripts/`:

- `infra/scripts/backup.sh` backs up PostgreSQL, protected resume storage, and application logs when those directories are mounted.
- `infra/scripts/restore.sh` restores a selected PostgreSQL dump and optional resume-storage archive.

Backups should be written to a protected directory such as `/var/backups/jobapp`, not to `frontend/public`, `.next`, `infra/nginx/html`, or any other public web directory. The scripts set owner-only permissions on backup directories and files where the host allows it.

Example environment variables for a maintenance container or VM shell:

```sh
export POSTGRES_DB=job_platform
export POSTGRES_USER=job_platform_app
export BACKUP_DIR=/var/backups/jobapp
export UPLOAD_DIR=/var/lib/jobapp/uploads
export LOG_DIR=/var/log/jobapp
```

Run a backup:

```sh
sh infra/scripts/backup.sh
```

Run a restore against a selected backup directory:

```sh
export BACKUP_PATH=/var/backups/jobapp/20260502T120000Z
sh infra/scripts/restore.sh
```

Test restore on a non-production database before relying on a backup for production recovery.

## Security Hardening

The backend uses response schemas, strict query/path validation, ORM-based queries, generic error handling, metadata-only audit logs, and log redaction for sensitive values. Audit/runtime logs must not include passwords, session tokens, reset tokens, API keys, full AI prompts, raw resume contents, generated cover letter text, edited cover letter text, or environment variables.

Job descriptions and scraped job fields are treated as untrusted data. The backend strips HTML before returning job display data, and the frontend should continue rendering untrusted content as text.

Public job browsing must not expose suspicious or inactive postings through public query flags; those moderation views belong behind admin-only `/admin/jobs` routes. Password reset tokens, resource IDs, external job URLs, AI-generated structured responses, and uploaded files all require backend allowlist validation.

Resume upload validation should compare the declared MIME type with content-derived validation and enforce DOCX archive limits to reduce forged MIME and archive-bomb risk. Do not print raw extracted resume text during local Gemini extraction debugging.

Nginx provides security headers, CSP, frame protection, referrer policy, request body size limits, and local HTTPS/TLS testing with a self-signed certificate. Standard local development still uses:

```powershell
docker compose up --build
```

To test HTTPS locally through the Dockerized Nginx reverse proxy:

```powershell
powershell -ExecutionPolicy Bypass -File .\infra\scripts\create-local-cert.ps1
docker compose -f docker-compose.yml -f docker-compose.local-tls.yml up -d --build
```

Open:

```text
https://localhost
```

The certificate is self-signed, so a browser warning is expected during local testing.

Repeatable security scan commands are documented in `infra/ci/security-checks.md`. The practical commands are:

```powershell
python -m pip install bandit semgrep pip-audit
bandit -r backend/app -x backend/app/tests
semgrep --config p/python --config p/owasp-top-ten backend/app
pip-audit --path backend
gitleaks detect --source . --no-git --redact
trivy config .
```

For frontend dependencies:

```powershell
cd frontend
npm audit --audit-level=high
cd ..
```

For container images, build first and then scan the produced images with Trivy.

## CI/CD

GitHub Actions workflows live under `.github/workflows/`:

- `ci-cd.yml` is the consolidated CI/CD workflow for backend tests, migration checks, frontend quality gates, security scanning, Docker validation/builds, and production deployment.
- The `Backend Tests` job installs the backend with dev dependencies, starts CI PostgreSQL and Redis services, and runs `pytest` with coverage.
- The `Database Migration Check` job inspects Alembic heads, applies migrations to a CI-only PostgreSQL service using placeholder credentials, and verifies the current migration.
- The `Frontend Checks` job installs frontend dependencies with `npm ci`, runs lint, typecheck, source/flow frontend tests, builds the app, and runs the Selenium smoke suite against a local Next server.
- The `Security Checks` job runs Bandit, Python dependency auditing, `npm audit`, Gitleaks, and Trivy filesystem/config/security scanning.
- The `Docker Build` job validates the Docker Compose configuration and builds the backend, frontend, worker, and beat images.
- The `Deploy To EC2` job runs only for manual workflow dispatch or pushes to `main` after all required jobs pass, then deploys to the configured EC2 host using repository secrets.

The workflows use read-only repository permissions and run on `push` and `pull_request` without `pull_request_target`, so untrusted pull request code is not executed with write tokens. CI is configured to fail closed on backend test failures, frontend lint/type/build failures, migration errors, committed secrets, and high or critical dependency/security findings.

Local equivalents:

```powershell
cd backend
python -m pip install -e ".[dev]"
python -m pytest --cov=app --cov-report=term-missing
alembic upgrade head
cd ..

cd frontend
npm ci
npm run lint
npm run typecheck
npm run test:auth-pages
npm run test:frontend-flows
npm run build
npm audit --audit-level=high
cd ..

bandit -r backend/app -x backend/app/tests --severity-level high
pip-audit backend --strict
gitleaks detect --source . --no-git --redact --exit-code 1
trivy fs --scanners vuln,secret,config --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 .
```

Use `.env.example` for placeholder variable names only. Keep real `.env` files local and untracked.

## Backend Development

From the `backend/` directory:

```powershell
python -m pip install -e ".[dev]"
python -m pytest
```

Run the backend directly after configuring environment variables:

```powershell
python -m uvicorn app.main:app --reload
```

## Database Migrations

From the `backend/` directory:

```powershell
alembic revision --autogenerate -m "initial schema"
alembic upgrade head
```

Do not run migrations against production without reviewing generated SQL.

When using Docker, prefer:

```powershell
docker compose run --rm backend alembic upgrade head
```

## Frontend Development

From the `frontend/` directory:

```powershell
npm install
npm run dev
```

The frontend expects API traffic to go through the reverse proxy in deployment.

Frontend tests:

```powershell
npm run test:auth-pages
npm run test:frontend-flows
npm run test:selenium
```

`test:frontend-flows` checks route composition, expected API endpoint wiring, protected-flow login redirects, upload constraints, and frontend security guardrails without requiring a live backend. `test:selenium` is a browser smoke test for every `src/app/**/page.tsx` route and the public auth forms. Install Selenium support from the backend directory with `python -m pip install -e ".[scrapers]"`, then start the frontend with `npm run dev`, or set `SELENIUM_BASE_URL` to a running frontend such as `http://localhost:8080`. The script skips when Selenium or the frontend is unavailable; set `SELENIUM_REQUIRE_BROWSER=1` or `SELENIUM_REQUIRE_SERVER=1` to make those hard failures.

## Security Notes

- Use `.env.example` only for variable names and placeholders.
- Store uploaded resumes outside public web roots.
- PostgreSQL and Redis are internal Docker services and are not exposed through host ports.
- Backend routes must enforce authentication, authorization, validation, safe errors, and audit logging when implemented.
- Scrapers must not execute at import time.
- Store logs and backups outside public web directories.
- Do not commit real `.env` files, API keys, database credentials, session secrets, or certificate private keys.
- Do not log raw AI prompts, resume contents, generated cover letters, passwords, reset tokens, session tokens, or API keys.
- Keep public job browsing limited to active, non-suspicious jobs; use admin routes for moderation filters.
- Validate resume content type from file content/signature and protect DOCX parsing from archive bombs.
- Validate structured AI output with response schemas before returning it to the frontend.
