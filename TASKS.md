# TASKS.md

# Implementation Tasks

## Purpose
This file is the implementation checklist for the Secure AI-Assisted Job Aggregation and Application Support Platform.

Use it with:
- `AGENTS.md` for coding-agent instructions.
- `PRD.md` for product requirements.
- `ARCHITECTURE.md` for system design, DFD, API areas, database schema, risks, and threat model.
- `CODING_GUIDELINES.md` for secure coding rules.

Security is part of every task. Do not treat security hardening as something only done at the end.

---

## Task Status Key
Use these statuses:

- `[ ]` Not started
- `[~]` In progress
- `[x]` Done
- `[!]` Blocked / needs decision

---

## Global Definition of Done
A task is only done when:

- Code is implemented.
- Input validation exists where input is accepted.
- Authorization checks exist where protected data is accessed.
- Security-relevant actions are audit logged.
- Sensitive values are not logged.
- User-facing errors are safe and generic.
- Tests are added or updated.
- Documentation is updated if behaviour or architecture changes.
- No secrets are committed.
- Docker/local setup still runs.

---

## Phase 0: Project Setup

### Repository and Documentation
- [x] Create repository structure.
- [x] Add `AGENTS.md`, `PRD.md`, `ARCHITECTURE.md`, `TASKS.md`, `CODING_GUIDELINES.md`.
- [x] Add `README.md` with local setup, test, lint, Docker, and deployment commands.
- [x] Add `docs/` directory for screenshots, diagrams, and report-related assets.
- [x] Add `.gitignore` for `.env`, uploaded files, generated keys, caches, build outputs, logs, local database files, and temporary worker files.
- [~] Add `.env.example` with placeholder values only.
- [~] Add `CHANGELOG.md` or simple release notes if useful.

### Backend Setup
- [x] Create backend FastAPI project.
- [x] Add backend package manager configuration, e.g. `pyproject.toml` or `requirements.txt`.
- [x] Add app entry point `backend/app/main.py`.
- [x] Add `backend/app/core/config.py` for typed environment configuration.
- [x] Add `backend/app/core/database.py`.
- [x] Add `backend/app/core/logging.py`.
- [x] Add `backend/app/api/` route modules.
- [x] Add `backend/app/models/`, `schemas/`, `services/`, `security/`, `workers/`, and `tests/`.
- [x] Add backend healthcheck endpoint, e.g. `GET /health`.

### Frontend Setup
- [x] Create frontend Next.js + TypeScript + Tailwind project.
- [ ] Add frontend environment example file if needed.
- [x] Add typed API client helper.
- [x] Add shared layout and navigation shell.
- [x] Add error boundary or safe error display component.
- [x] Add loading states and empty states.

### Docker and Local Environment
- [x] Create Docker Compose with frontend, backend, PostgreSQL, Redis, worker, and Nginx.
- [ ] Add development Docker Compose profile.
- [ ] Add production Docker Compose profile.
- [x] Add Dockerfiles for backend, frontend, worker, and Nginx if needed.
- [x] Add container healthchecks.
- [x] Ensure PostgreSQL and Redis are internal-only in Docker networking.
- [ ] Add local startup script if useful, e.g. `infra/scripts/dev-up.sh`.
- [ ] Add local reset script if useful, e.g. `infra/scripts/reset-db.sh`.

### Baseline Security Setup
- [~] Add dependency lock files.
- [ ] Add Bandit or Semgrep baseline command.
- [ ] Add Gitleaks configuration or command.
- [ ] Add Trivy command for image scanning if Docker images are built.
- [x] Add secure default config values for local development.
- [x] Ensure debug mode is controlled by environment variable and defaults safely.

---

## Phase 1: Database and Migrations

### Migration Setup
- [x] Set up SQLAlchemy models.
- [x] Set up Alembic migrations.
- [x] Add database session dependency.
- [x] Add migration command to README.
- [ ] Add seed command for local/demo data.

### Core Account Tables
- [x] Implement `users` table.
- [x] Implement `sessions` table.
- [x] Implement `password_reset_tokens` table.
- [x] Implement `user_profiles` table.
- [x] Add indexes for email, session token hash, reset token hash, and user references.
- [x] Add constraints for roles, active status, and unique email.

### Resume Tables
- [x] Implement `resumes` table.
- [x] Implement `resume_extractions` table.
- [x] Add indexes on `user_id`, `resume_id`, `file_hash`, and processing status.
- [x] Ensure resume records support upload status and parsing status.

### Job Tables
- [x] Implement `job_sources` table.
- [x] Implement `scraping_runs` table.
- [x] Implement `job_postings` table.
- [x] Add uniqueness for source/external job ID where available.
- [x] Add content hash for duplicate detection.
- [x] Add `is_active` and `is_suspicious` fields.
- [x] Add indexes for search fields such as title, company, location, category, source, and posting date.

### User Activity Tables
- [x] Implement `saved_jobs` table.
- [x] Implement `recommendations` table.
- [x] Implement `cover_letters` table.
- [x] Implement `application_history` table.
- [x] Add ownership-enforcing foreign keys and indexes.

### Audit and Operations Tables
- [x] Implement `audit_logs` table.
- [x] Add structured `details_json` field.
- [x] Add indexes for `user_id`, `event_type`, `target_type`, `target_id`, `created_at`, and `outcome`.
- [x] Add retention-ready timestamp fields.

### Seed Data
- [x] Add seed data for approved job sources.
- [x] Add safe initial admin creation flow.
- [x] Ensure initial admin password is not hardcoded.
- [x] Document how to create the first admin securely.

---

## Phase 2: Authentication and Account Management

### Password and Session Foundations
- [x] Implement password hashing using Argon2id or bcrypt.
- [x] Add password verification helper.
- [x] Add secure random token generation helper.
- [x] Add token hashing helper for session and reset tokens.
- [x] Implement session expiry.
- [x] Implement session revocation.
- [x] Implement secure cookie/session handling.
- [x] Ensure cookie settings support `HttpOnly`, `Secure` in production, and `SameSite=Lax` or `Strict`.

### Registration
- [x] Implement registration endpoint.
- [x] Validate email format.
- [x] Validate password minimum requirements.
- [x] Prevent duplicate active accounts.
- [x] Return safe duplicate/generic errors where appropriate.
- [x] Create default user profile row.
- [x] Add audit logging for registration success/failure.
- [x] Add registration tests.

### Login and Logout
- [x] Implement login endpoint.
- [x] Use generic login errors.
- [x] Implement failed login tracking.
- [x] Implement account lockout or progressive delay after repeated failed attempts.
- [x] Implement logout endpoint.
- [x] Invalidate session on logout.
- [x] Add audit logging for login success/failure and logout.
- [x] Add login/logout tests.

### Account Profile
- [x] Implement authenticated `GET /me`.
- [x] Implement account profile update.
- [x] Validate profile fields.
- [x] Prevent users from updating protected fields such as role directly.
- [x] Add audit logging for profile update.
- [x] Add profile tests.

### Account Deletion
- [x] Implement account deletion with re-authentication or equivalent verification.
- [x] Decide soft delete vs hard delete.
- [x] Ensure deletion does not leave corrupted references.
- [x] Invalidate sessions after deletion.
- [x] Add audit logging for deletion request and result.
- [x] Add account deletion tests.

### Password Change
- [x] Implement password change for authenticated users.
- [x] Require current password.
- [x] Invalidate other sessions after password change if appropriate.
- [x] Add audit logging.
- [x] Add password change tests.

### Password Reset
- [x] Implement password reset request endpoint.
- [x] Use generic response regardless of email existence.
- [x] Generate secure random reset token.
- [x] Store reset token hash only.
- [x] Make reset token single-use and time-limited.
- [x] Implement reset confirmation endpoint.
- [x] Invalidate used token.
- [x] Invalidate sessions after successful reset if appropriate.
- [x] Add audit logging for reset request and completion.
- [x] Add tests for expired, invalid, and reused reset tokens.

### Auth Rate Limiting
- [x] Implement rate limiting for registration.
- [x] Implement rate limiting for login.
- [x] Implement rate limiting for password reset request.
- [~] Add tests or documented manual verification for rate limits.

---

## Phase 3: Authorization and RBAC

### RBAC Foundations
- [x] Implement role enum: `USER`, `ADMIN`.
- [x] Implement authentication dependency.
- [x] Implement admin-only dependency.
- [x] Implement ownership-check helper.
- [x] Implement `assert_owner_or_admin` helper.
- [x] Add standard authorization error format.

### Protected Resources
- [x] Add backend authorization to every protected endpoint.
- [x] Enforce user ownership on account/profile routes.
- [x] Enforce user ownership on resume routes.
- [x] Enforce user ownership on resume extraction routes.
- [x] Enforce user ownership on saved job routes.
- [x] Enforce user ownership on recommendation routes.
- [x] Enforce user ownership on cover letter routes.
- [x] Enforce user ownership on application history routes.
- [x] Enforce admin role on all admin routes.

### Authorization Logging and Tests
- [x] Add audit logging for failed authorization attempts.
- [x] Add tests proving users cannot access another user's profile.
- [x] Add tests proving users cannot access another user's resume.
- [x] Add tests proving users cannot access another user's saved jobs.
- [x] Add tests proving users cannot access another user's recommendations.
- [x] Add tests proving users cannot access another user's cover letters.
- [x] Add tests proving normal users cannot access admin endpoints.

---

## Phase 4: Frontend Account Flows

### Shared Frontend Foundation
- [x] Create layout and navigation.
- [x] Create authenticated route handling.
- [x] Create safe API error handler.
- [x] Create reusable form components.
- [x] Create loading and empty states.
- [x] Ensure frontend does not store session tokens in localStorage.

### Auth Pages
- [x] Create register page.
- [x] Create login page.
- [x] Create logout action.
- [x] Create forgot password page.
- [x] Create reset password page.
- [x] Display safe generic errors only.

### Account Pages
- [x] Create account/profile page.
- [x] Create profile update form.
- [x] Create change password form.
- [x] Create delete account flow with re-authentication.
- [x] Add success and failure messages without exposing internals.

### Frontend Tests
- [x] Add basic frontend tests for auth pages if test framework is included.
- [x] Add manual test checklist for auth flows.

---

## Phase 5: Job Sources, Scraping, and Job Data

### Job Source Management
- [~] Implement job source model and admin CRUD for enabled/disabled sources.
- [x] Ensure only admins can create/update/disable job sources.
- [x] Validate source base URL.
- [x] Prevent unapproved source scraping.
- [x] Add audit logging for source management.

### Scraper Framework
- [x] Implement scraper service interface.
- [x] Implement at least one approved source adapter or mock adapter for coursework.
- [x] Add adapter for JobStreet if feasible.
- [x] Add adapter for MyCareersFuture if feasible.
- [x] If real scraping is not feasible, implement seeded/mock scraper with the same data model and logs.
- [x] Respect source allowlist.
- [x] Handle network failures safely.
- [x] Add retry policy with limits.
- [x] Add timeout for scraping requests.

### Job Normalization and Validation
- [x] Normalize job fields: title, company, location, category, description, source, posting date, application link.
- [x] Validate required fields: title, company, source, application link.
- [x] Validate job URLs.
- [x] Store source attribution.
- [x] Store scraped timestamp.
- [x] Implement content hash.
- [x] Implement duplicate detection using source ID, external job ID, normalized fields, and/or content hash.
- [x] Flag malformed jobs.
- [x] Flag suspicious jobs.

### Scraping Runs
- [x] Implement scraping run records.
- [x] Track started time, completed time, source, status, jobs retrieved, and safe error message.
- [x] Implement weekly scheduled scraping task.
- [x] Add manual trigger for admin if needed.
- [x] Add admin view/API for scraping success/failure and jobs retrieved.
- [x] Add audit logging for scraping failures and admin-triggered scraping.

### Tests
- [x] Add tests for job normalization.
- [x] Add tests for duplicate detection.
- [x] Add tests for suspicious job flagging.
- [x] Add tests for source allowlist enforcement.
- [x] Add tests for scraper failure handling.

---

## Phase 6: Job Browsing and Saved Jobs

### Job Search API
- [x] Implement `GET /jobs` with keyword filter.
- [x] Implement company filter.
- [x] Implement location filter.
- [x] Implement category filter.
- [x] Implement active-only filtering by default.
- [x] Add pagination.
- [x] Add query size limits.
- [x] Prevent expensive unbounded queries.
- [x] Use ORM/parameterized queries only.

### Job Detail API
- [x] Implement `GET /jobs/{job_id}`.
- [x] Sanitize/encode job descriptions for display.
- [x] Do not render untrusted HTML unsafely.
- [x] Validate external job URLs against approved source domains.
- [x] Add external link warning behaviour.
- [x] Hide or mark suspicious/inactive jobs appropriately.

### Saved Jobs
- [x] Implement save job endpoint.
- [x] Implement unsave job endpoint.
- [x] Implement list saved jobs endpoint.
- [x] Ensure users can only view and manage their own saved jobs.
- [x] Add audit logging for saved job changes if required.

### Frontend
- [x] Build frontend job listing page.
- [x] Build frontend job filter/search UI.
- [x] Build frontend job detail page.
- [x] Build frontend saved jobs page.
- [x] Add external link warning UI.
- [x] Add safe display for job descriptions.

### Tests
- [x] Add tests for job search.
- [x] Add tests for filters.
- [x] Add tests for pagination.
- [x] Add tests for job detail.
- [x] Add tests for saved jobs access control.
- [x] Add tests for XSS payloads in job descriptions.

---

## Phase 7: Secure Resume Upload and Extraction

### Secure Storage
- [x] Implement protected resume storage directory outside public web root.
- [x] Ensure storage path is configurable.
- [x] Ensure storage directory is not served by Nginx.
- [x] Generate randomized stored filename.
- [x] Store original filename only as metadata.
- [x] Store file hash.
- [x] Prevent path traversal.

### Upload Validation
- [x] Implement file allowlist for PDF and DOCX.
- [x] Implement file extension validation.
- [x] Implement MIME validation.
- [x] Implement basic file signature/content validation.
- [x] Implement file size limit.
- [x] Reject empty files.
- [x] Reject unsupported files with safe error message.
- [x] Add rate limiting for upload endpoint.

### Upload API
- [x] Create resume upload endpoint.
- [x] Create resume list endpoint.
- [x] Create resume detail endpoint.
- [x] Create resume delete endpoint if required.
- [x] Enforce resume ownership on all resume endpoints.
- [x] Add audit logging for upload success/failure.

### Extraction Worker
- [x] Enqueue extraction task after upload.
- [x] Implement worker task for resume parsing.
- [x] Add parser timeout.
- [x] Add memory/resource safeguards where practical.
- [x] Handle parser failure safely.
- [x] Store extracted skills, education, experience, and years of experience.
- [x] Store processing status.
- [x] Add audit logging for extraction success/failure.
- [x] Ensure full resume content is not written to ordinary logs.

### Profile Review
- [x] Allow user to view extracted profile.
- [x] Allow user to edit extracted profile.
- [x] Validate edited profile fields.
- [x] Add audit logging for profile edits.

### Frontend
- [x] Build frontend resume upload page.
- [x] Build frontend upload status page or component.
- [x] Build frontend extracted profile review page.
- [x] Build frontend extracted profile edit page.

### Tests
- [x] Add tests for valid PDF upload.
- [x] Add tests for valid DOCX upload.
- [x] Add tests for invalid file extension rejection.
- [x] Add tests for invalid MIME rejection.
- [x] Add tests for oversized file rejection.
- [x] Add tests for path traversal filename rejection.
- [x] Add tests for unauthorized resume access.
- [x] Add tests for extraction failure handling.

---

## Phase 8: Recommendations

### Recommendation Engine
- [x] Implement recommendation scoring service.
- [x] Use extracted skills, experience, education, and job fields.
- [x] Add simple baseline matching first, then improve if time permits.
- [x] Store match score.
- [x] Store recommendation rationale.
- [x] Ensure recommendation belongs to the requesting user.
- [x] Avoid leaking other users' profile data.

### Recommendation API
- [x] Implement recommendation refresh endpoint.
- [x] Implement list recommendations endpoint.
- [x] Rate limit recommendation refresh.
- [x] Reviewed worker need: current deterministic refresh is bounded and safe to keep synchronous for Phase 8; queue only `user_id` in a future worker path if scoring becomes long-running or AI-backed.
- [x] Add audit logging for recommendation generation.

### Frontend
- [x] Build frontend recommendations page.
- [x] Add refresh recommendation action.
- [x] Show match score and rationale safely.
- [x] Add empty state if no resume/profile exists.

### Tests
- [x] Add tests for recommendation generation.
- [x] Add tests for recommendation ownership.
- [x] Add tests for refresh after profile update.
- [x] Add tests for rate-limited refresh if feasible.

---

## Phase 9: Cover Letter Drafts

### AI Prompt Safety
- [ ] Implement AI prompt builder with separated trusted instructions and untrusted content.
- [ ] Add delimiters around resume/profile/job content.
- [ ] Minimize personal data sent to AI service.
- [ ] Add prompt length limits.
- [ ] Treat AI output as untrusted until displayed safely.
- [ ] Do not log full prompts containing personal data.

### Cover Letter API
- [ ] Implement cover letter generation endpoint.
- [ ] Rate limit cover letter generation.
- [ ] Store generated draft.
- [ ] Allow user to view own drafts.
- [ ] Allow user to edit cover letter draft.
- [ ] Save edited version or edited text.
- [ ] Never auto-submit cover letters to external platforms.
- [ ] Add application history record when draft is generated or edited.
- [ ] Add audit logging for generation/editing.

### Frontend
- [ ] Build frontend cover letter draft page.
- [ ] Add generate draft button on job detail/recommendation page.
- [ ] Add cover letter editor.
- [ ] Add clear label that AI output is a draft and must be reviewed.
- [ ] Add save edited draft action.

### Tests
- [ ] Add tests for cover letter generation ownership.
- [ ] Add tests for cover letter editing ownership.
- [ ] Add tests for another user being blocked from reading a draft.
- [ ] Add tests for application history creation.
- [ ] Add tests for rate limiting if feasible.

---

## Phase 10: Application History

### Backend
- [ ] Implement application history model usage.
- [ ] Track cover letter generation.
- [ ] Track cover letter edits if required.
- [ ] Track saved/prepared job actions if required.
- [ ] Implement `GET /application-history`.
- [ ] Ensure users can only see own history.
- [ ] Add pagination.
- [ ] Add safe filters if needed.

### Frontend
- [ ] Build frontend application history page.
- [ ] Show job title, company, action type, and action time.
- [ ] Link to related cover letter draft where authorized.
- [ ] Add empty state.

### Tests
- [ ] Add tests for application history access control.
- [ ] Add tests for generated cover letter appearing in history.
- [ ] Add tests for pagination.

---

## Phase 11: Admin Dashboard

### Admin Access
- [x] Require admin role for all admin endpoints.
- [ ] Add stronger admin authentication policy if feasible.
- [~] Add audit logging for every admin action.
- [x] Add tests proving normal users cannot access admin routes.

### User Management
- [ ] Implement admin user list.
- [ ] Implement user detail view.
- [ ] Implement user activation/deactivation if needed.
- [ ] Prevent unsafe admin password reset to known value.
- [ ] Log admin user management actions.

### Job Moderation
- [ ] Implement admin job review list.
- [ ] Implement suspicious job review.
- [ ] Implement admin job disable/enable.
- [ ] Log job moderation actions.

### Scraping Monitoring
- [x] Implement scraping run list.
- [ ] Implement scraping run detail.
- [x] Show successful runs, failed runs, and jobs retrieved.
- [x] Show safe error messages only.

### Audit Logs and Health
- [ ] Implement audit log viewer.
- [ ] Add filtering by event type, user, date, and outcome if feasible.
- [x] Implement service health/monitoring endpoint.
- [ ] Include background worker status if feasible.
- [ ] Include database/Redis connectivity status if feasible.

### Frontend
- [ ] Build frontend admin dashboard.
- [ ] Build admin users page.
- [ ] Build admin jobs page.
- [ ] Build admin scraping runs page.
- [ ] Build admin audit logs page.
- [ ] Build admin health page.

### Tests
- [~] Add tests for admin-only endpoints.
- [ ] Add tests for admin job disable/enable.
- [ ] Add tests for admin audit log access.
- [~] Add tests that admin actions create audit logs.

---

## Phase 12: Security Hardening

### Input/Output Security
- [~] Add global input validation and schema validation.
- [x] Add output encoding/sanitization strategy.
- [~] Add HTML sanitizer if rich job descriptions are displayed.
- [x] Add tests for XSS payloads.
- [ ] Add tests for SQL injection attempts.

### HTTP and Browser Security
- [x] Add security headers in Nginx.
- [x] Add Content Security Policy.
- [x] Add `X-Content-Type-Options: nosniff`.
- [x] Add `Referrer-Policy`.
- [x] Add frame protection via CSP or `X-Frame-Options`.
- [x] Add request size limits.
- [ ] Ensure HTTPS/TLS is configured for deployment.

### Production Safety
- [x] Ensure debug mode is disabled in production.
- [x] Ensure frontend does not expose secrets.
- [x] Ensure backend does not return internal errors.
- [x] Ensure Redis is not exposed publicly.
- [x] Ensure PostgreSQL is not exposed publicly.
- [x] Ensure uploaded files are not exposed publicly.
- [~] Ensure logs/backups are not in public directories.

### Logging and Sensitive Data
- [x] Ensure logs do not contain passwords.
- [x] Ensure logs do not contain reset tokens.
- [x] Ensure logs do not contain session tokens.
- [~] Ensure logs do not contain API keys.
- [x] Ensure logs do not contain full resume content.
- [ ] Ensure logs do not contain full AI prompts with personal data.
- [x] Add log redaction helper if needed.

### Availability and Abuse Protection
- [~] Add rate limiting to login, reset, upload, recommendation, and cover letter endpoints.
- [x] Add account lockout or progressive delay after repeated failed login attempts.
- [x] Add upload size limits at Nginx and backend.
- [ ] Add worker task timeouts.
- [ ] Add queue limits or backpressure if feasible.
- [x] Add pagination limits for list endpoints.

### Backup and Restore
- [ ] Add database backup script.
- [ ] Add protected file storage backup script if required.
- [ ] Add audit log backup/retention plan.
- [ ] Add restore test script or documented restore procedure.
- [ ] Ensure backups are protected from public access.

### Security Scanning
- [ ] Add dependency scanning.
- [ ] Add secret scanning.
- [ ] Add container image scanning.
- [ ] Add SAST scanning.
- [ ] Document any accepted false positives.

---

## Phase 13: Testing

### Backend Unit Tests
- [x] Add backend unit tests for auth.
- [x] Add backend unit tests for password hashing.
- [x] Add backend unit tests for reset token hashing/expiry.
- [x] Add backend unit tests for authorization helpers.
- [x] Add backend unit tests for file validation.
- [x] Add backend unit tests for job normalization.
- [x] Add backend unit tests for duplicate detection.
- [x] Add backend unit tests for recommendation scoring.
- [ ] Add backend unit tests for AI prompt builder.
- [~] Add backend unit tests for audit logging helper.

### Backend Integration Tests
- [ ] Add integration tests for account CRUD.
- [x] Add integration tests for login/logout/session expiry.
- [x] Add integration tests for password reset.
- [~] Add integration tests for resume upload and extraction task.
- [x] Add integration tests for job search and saved jobs.
- [x] Add integration tests for recommendation generation.
- [ ] Add integration tests for cover letter generation flow.
- [ ] Add integration tests for application history.
- [~] Add integration tests for admin controls.

### Security Tests
- [x] Add security tests for broken access control.
- [x] Add security tests for invalid file uploads.
- [x] Add security tests for path traversal upload filenames.
- [x] Add security tests for generic login/reset errors.
- [ ] Add security tests for SQL injection attempts.
- [~] Add security tests for XSS payloads in job descriptions/profile fields.
- [x] Add security tests for unauthorized admin access.
- [x] Add security tests checking sensitive values are not logged.

### Frontend Tests
- [x] Add frontend lint.
- [x] Add frontend type check.
- [x] Add frontend build test.
- [ ] Add component tests for key forms if feasible.
- [ ] Add manual test checklist for full user journey.

### Coverage
- [ ] Achieve at least 70% unit test coverage for critical backend modules.
- [ ] Generate coverage report.
- [ ] Document any untested critical path and reason.

---

## Phase 14: CI/CD

### GitHub Actions
- [ ] Add GitHub Actions workflow for backend tests.
- [ ] Add GitHub Actions workflow for frontend lint/build.
- [ ] Add workflow for database migration check if feasible.
- [ ] Add workflow caching for dependencies.

### Security Checks
- [ ] Add Bandit or Semgrep scan.
- [ ] Add dependency vulnerability scan.
- [ ] Add Gitleaks secret scan.
- [ ] Add Trivy container scan if Docker image is built.
- [ ] Fail CI on committed secrets.
- [ ] Fail CI on critical security findings unless documented and accepted.

### Quality Gates
- [ ] CI fails on backend test failure.
- [ ] CI fails on frontend lint/build failure.
- [ ] CI fails on type errors.
- [ ] CI fails on migration errors.
- [ ] Add status badge to README if useful.

---

## Phase 15: Deployment

### AWS VM Preparation
- [ ] Configure provided AWS VM.
- [ ] Ensure SSH access works with provided key.
- [ ] Update system packages.
- [ ] Install Docker and Docker Compose.
- [ ] Configure firewall/security group.
- [ ] Verify only required ports are open.
- [ ] Ensure web frontend is served from provided AWS VM.

### Nginx and TLS
- [ ] Configure Nginx reverse proxy.
- [ ] Configure HTTPS/TLS.
- [ ] Add HTTP to HTTPS redirect if domain/cert setup allows.
- [ ] Add Nginx request size limits.
- [ ] Add Nginx security headers.

### Application Deployment
- [ ] Configure Docker Compose production profile.
- [ ] Configure environment variables on AWS VM.
- [ ] Run database migrations.
- [ ] Create initial admin account securely.
- [ ] Verify backend healthcheck.
- [ ] Verify frontend loads.
- [ ] Verify background worker is running.
- [ ] Verify Redis is internal.
- [ ] Verify PostgreSQL is internal.
- [ ] Verify uploaded files are stored in protected storage.

### Scheduled Jobs and Backups
- [ ] Verify scraping schedule.
- [ ] Verify scraping run logs.
- [ ] Verify backup schedule.
- [ ] Verify backup location is protected.
- [ ] Run restore test or document restore test result.

### Post-Deployment Verification
- [ ] Run smoke tests after deployment.
- [ ] Test registration/login/logout.
- [ ] Test job browsing.
- [ ] Test resume upload.
- [ ] Test recommendation generation.
- [ ] Test cover letter draft generation.
- [ ] Test admin dashboard access.
- [ ] Test normal user cannot access admin dashboard.
- [ ] Verify logs and audit events.
- [ ] Verify no stack traces are exposed to users.

---

## Phase 16: Documentation and Report Support

### Developer Documentation
- [ ] Update README with setup instructions.
- [ ] Document environment variables.
- [ ] Document database migration commands.
- [ ] Document test commands.
- [ ] Document deployment commands.
- [ ] Document backup/restore commands.

### Security Documentation
- [ ] Document security assumptions.
- [ ] Document threat model summary.
- [ ] Document attack surface summary.
- [ ] Document security controls implemented.
- [ ] Document accepted risks or limitations.
- [ ] Document dependency/security scan results.

### Demo Preparation
- [ ] Prepare demo accounts.
- [ ] Prepare demo job postings.
- [ ] Prepare safe sample resume.
- [ ] Prepare admin dashboard demo.
- [ ] Prepare security test/demo screenshots.
- [ ] Prepare final smoke test checklist.

---

## Risk-to-Task Traceability

| Risk | Related Tasks |
|---|---|
| R1 Data leakage of resumes, profiles, cover letters | Phase 2, Phase 3, Phase 7, Phase 10, Phase 12, Phase 13 |
| R2 Account takeover | Phase 2, Phase 12, Phase 13 |
| R3 Broken access control / privilege escalation | Phase 3, Phase 11, Phase 13 |
| R4 Malicious resume upload | Phase 7, Phase 12, Phase 13 |
| R5 Job poisoning / XSS / malicious redirect | Phase 5, Phase 6, Phase 12, Phase 13 |
| R6 Prompt injection / AI misuse | Phase 8, Phase 9, Phase 12, Phase 13 |
| R7 DoS / resource exhaustion | Phase 2, Phase 6, Phase 7, Phase 8, Phase 9, Phase 12 |
| R8 Log tampering / sensitive data in logs | Phase 11, Phase 12, Phase 13 |
| R9 Insecure secrets / vulnerable dependencies | Phase 0, Phase 14, Phase 15 |
| R10 Backup exposure or recovery failure | Phase 12, Phase 15 |
| R11 Misleading recommendation / cover letter output | Phase 8, Phase 9, Phase 16 |
| R12 Scraping failure or stale job data | Phase 5, Phase 11, Phase 15 |

---

## MVP Definition
The MVP is complete when:

- Account registration/login/logout/password reset works securely.
- User profile CRUD works.
- Resume upload with secure validation works.
- Resume extraction produces editable profile information.
- Job postings can be seeded or scraped, searched, filtered, and viewed.
- Duplicate/suspicious job handling exists.
- Saved jobs works.
- Recommendation generation works.
- Cover letter draft generation/editing works.
- Application history works.
- Admin can view scraping runs, review jobs, manage users, and inspect audit logs.
- RBAC and ownership checks prevent unauthorized access.
- Security-relevant events are logged.
- Critical tests and security scans pass.
- Docker Compose deployment works on the provided AWS VM.
- PostgreSQL and Redis are not publicly exposed.
- Uploaded resumes are not publicly exposed.
- No secrets are committed.

---

## Stretch Goals
Only attempt these after MVP is complete:

- [ ] Add MFA for admin accounts.
- [ ] Add email verification for registration.
- [ ] Add CAPTCHA after repeated failed login attempts.
- [ ] Add richer recommendation algorithm.
- [ ] Add multiple real job source adapters.
- [ ] Add full-text search using PostgreSQL `tsvector`.
- [ ] Add admin export of scraping statistics.
- [ ] Add anomaly detection for suspicious login or generation behaviour.
- [ ] Add automated backup encryption key rotation.
- [ ] Add security dashboard summarizing failed logins, blocked uploads, and suspicious jobs.
