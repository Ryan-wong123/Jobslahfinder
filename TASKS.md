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
- [ ] Create repository structure.
- [ ] Add `AGENTS.md`, `PRD.md`, `ARCHITECTURE.md`, `TASKS.md`, `CODING_GUIDELINES.md`.
- [ ] Add `README.md` with local setup, test, lint, Docker, and deployment commands.
- [ ] Add `docs/` directory for screenshots, diagrams, and report-related assets.
- [ ] Add `.gitignore` for `.env`, uploaded files, generated keys, caches, build outputs, logs, local database files, and temporary worker files.
- [ ] Add `.env.example` with placeholder values only.
- [ ] Add `CHANGELOG.md` or simple release notes if useful.

### Backend Setup
- [ ] Create backend FastAPI project.
- [ ] Add backend package manager configuration, e.g. `pyproject.toml` or `requirements.txt`.
- [ ] Add app entry point `backend/app/main.py`.
- [ ] Add `backend/app/core/config.py` for typed environment configuration.
- [ ] Add `backend/app/core/database.py`.
- [ ] Add `backend/app/core/logging.py`.
- [ ] Add `backend/app/api/` route modules.
- [ ] Add `backend/app/models/`, `schemas/`, `services/`, `security/`, `workers/`, and `tests/`.
- [ ] Add backend healthcheck endpoint, e.g. `GET /health`.

### Frontend Setup
- [ ] Create frontend Next.js + TypeScript + Tailwind project.
- [ ] Add frontend environment example file if needed.
- [ ] Add typed API client helper.
- [ ] Add shared layout and navigation shell.
- [ ] Add error boundary or safe error display component.
- [ ] Add loading states and empty states.

### Docker and Local Environment
- [ ] Create Docker Compose with frontend, backend, PostgreSQL, Redis, worker, and Nginx.
- [ ] Add development Docker Compose profile.
- [ ] Add production Docker Compose profile.
- [ ] Add Dockerfiles for backend, frontend, worker, and Nginx if needed.
- [ ] Add container healthchecks.
- [ ] Ensure PostgreSQL and Redis are internal-only in Docker networking.
- [ ] Add local startup script if useful, e.g. `infra/scripts/dev-up.sh`.
- [ ] Add local reset script if useful, e.g. `infra/scripts/reset-db.sh`.

### Baseline Security Setup
- [ ] Add dependency lock files.
- [ ] Add Bandit or Semgrep baseline command.
- [ ] Add Gitleaks configuration or command.
- [ ] Add Trivy command for image scanning if Docker images are built.
- [ ] Add secure default config values for local development.
- [ ] Ensure debug mode is controlled by environment variable and defaults safely.

---

## Phase 1: Database and Migrations

### Migration Setup
- [ ] Set up SQLAlchemy models.
- [ ] Set up Alembic migrations.
- [ ] Add database session dependency.
- [ ] Add migration command to README.
- [ ] Add seed command for local/demo data.

### Core Account Tables
- [ ] Implement `users` table.
- [ ] Implement `sessions` table.
- [ ] Implement `password_reset_tokens` table.
- [ ] Implement `user_profiles` table.
- [ ] Add indexes for email, session token hash, reset token hash, and user references.
- [ ] Add constraints for roles, active status, and unique email.

### Resume Tables
- [ ] Implement `resumes` table.
- [ ] Implement `resume_extractions` table.
- [ ] Add indexes on `user_id`, `resume_id`, `file_hash`, and processing status.
- [ ] Ensure resume records support upload status and parsing status.

### Job Tables
- [ ] Implement `job_sources` table.
- [ ] Implement `scraping_runs` table.
- [ ] Implement `job_postings` table.
- [ ] Add uniqueness for source/external job ID where available.
- [ ] Add content hash for duplicate detection.
- [ ] Add `is_active` and `is_suspicious` fields.
- [ ] Add indexes for search fields such as title, company, location, category, source, and posting date.

### User Activity Tables
- [ ] Implement `saved_jobs` table.
- [ ] Implement `recommendations` table.
- [ ] Implement `cover_letters` table.
- [ ] Implement `application_history` table.
- [ ] Add ownership-enforcing foreign keys and indexes.

### Audit and Operations Tables
- [ ] Implement `audit_logs` table.
- [ ] Add structured `details_json` field.
- [ ] Add indexes for `user_id`, `event_type`, `target_type`, `target_id`, `created_at`, and `outcome`.
- [ ] Add retention-ready timestamp fields.

### Seed Data
- [ ] Add seed data for approved job sources.
- [ ] Add safe initial admin creation flow.
- [ ] Ensure initial admin password is not hardcoded.
- [ ] Document how to create the first admin securely.

---

## Phase 2: Authentication and Account Management

### Password and Session Foundations
- [ ] Implement password hashing using Argon2id or bcrypt.
- [ ] Add password verification helper.
- [ ] Add secure random token generation helper.
- [ ] Add token hashing helper for session and reset tokens.
- [ ] Implement session expiry.
- [ ] Implement session revocation.
- [ ] Implement secure cookie/session handling.
- [ ] Ensure cookie settings support `HttpOnly`, `Secure` in production, and `SameSite=Lax` or `Strict`.

### Registration
- [ ] Implement registration endpoint.
- [ ] Validate email format.
- [ ] Validate password minimum requirements.
- [ ] Prevent duplicate active accounts.
- [ ] Return safe duplicate/generic errors where appropriate.
- [ ] Create default user profile row.
- [ ] Add audit logging for registration success/failure.
- [ ] Add registration tests.

### Login and Logout
- [ ] Implement login endpoint.
- [ ] Use generic login errors.
- [ ] Implement failed login tracking.
- [ ] Implement account lockout or progressive delay after repeated failed attempts.
- [ ] Implement logout endpoint.
- [ ] Invalidate session on logout.
- [ ] Add audit logging for login success/failure and logout.
- [ ] Add login/logout tests.

### Account Profile
- [ ] Implement authenticated `GET /me`.
- [ ] Implement account profile update.
- [ ] Validate profile fields.
- [ ] Prevent users from updating protected fields such as role directly.
- [ ] Add audit logging for profile update.
- [ ] Add profile tests.

### Account Deletion
- [ ] Implement account deletion with re-authentication or equivalent verification.
- [ ] Decide soft delete vs hard delete.
- [ ] Ensure deletion does not leave corrupted references.
- [ ] Invalidate sessions after deletion.
- [ ] Add audit logging for deletion request and result.
- [ ] Add account deletion tests.

### Password Change
- [ ] Implement password change for authenticated users.
- [ ] Require current password.
- [ ] Invalidate other sessions after password change if appropriate.
- [ ] Add audit logging.
- [ ] Add password change tests.

### Password Reset
- [ ] Implement password reset request endpoint.
- [ ] Use generic response regardless of email existence.
- [ ] Generate secure random reset token.
- [ ] Store reset token hash only.
- [ ] Make reset token single-use and time-limited.
- [ ] Implement reset confirmation endpoint.
- [ ] Invalidate used token.
- [ ] Invalidate sessions after successful reset if appropriate.
- [ ] Add audit logging for reset request and completion.
- [ ] Add tests for expired, invalid, and reused reset tokens.

### Auth Rate Limiting
- [ ] Implement rate limiting for registration.
- [ ] Implement rate limiting for login.
- [ ] Implement rate limiting for password reset request.
- [ ] Add tests or documented manual verification for rate limits.

---

## Phase 3: Authorization and RBAC

### RBAC Foundations
- [ ] Implement role enum: `USER`, `ADMIN`.
- [ ] Implement authentication dependency.
- [ ] Implement admin-only dependency.
- [ ] Implement ownership-check helper.
- [ ] Implement `assert_owner_or_admin` helper.
- [ ] Add standard authorization error format.

### Protected Resources
- [ ] Add backend authorization to every protected endpoint.
- [ ] Enforce user ownership on account/profile routes.
- [ ] Enforce user ownership on resume routes.
- [ ] Enforce user ownership on resume extraction routes.
- [ ] Enforce user ownership on saved job routes.
- [ ] Enforce user ownership on recommendation routes.
- [ ] Enforce user ownership on cover letter routes.
- [ ] Enforce user ownership on application history routes.
- [ ] Enforce admin role on all admin routes.

### Authorization Logging and Tests
- [ ] Add audit logging for failed authorization attempts.
- [ ] Add tests proving users cannot access another user's profile.
- [ ] Add tests proving users cannot access another user's resume.
- [ ] Add tests proving users cannot access another user's saved jobs.
- [ ] Add tests proving users cannot access another user's recommendations.
- [ ] Add tests proving users cannot access another user's cover letters.
- [ ] Add tests proving normal users cannot access admin endpoints.

---

## Phase 4: Frontend Account Flows

### Shared Frontend Foundation
- [ ] Create layout and navigation.
- [ ] Create authenticated route handling.
- [ ] Create safe API error handler.
- [ ] Create reusable form components.
- [ ] Create loading and empty states.
- [ ] Ensure frontend does not store session tokens in localStorage.

### Auth Pages
- [ ] Create register page.
- [ ] Create login page.
- [ ] Create logout action.
- [ ] Create forgot password page.
- [ ] Create reset password page.
- [ ] Display safe generic errors only.

### Account Pages
- [ ] Create account/profile page.
- [ ] Create profile update form.
- [ ] Create change password form.
- [ ] Create delete account flow with re-authentication.
- [ ] Add success and failure messages without exposing internals.

### Frontend Tests
- [ ] Add basic frontend tests for auth pages if test framework is included.
- [ ] Add manual test checklist for auth flows.

---

## Phase 5: Job Sources, Scraping, and Job Data

### Job Source Management
- [ ] Implement job source model and admin CRUD for enabled/disabled sources.
- [ ] Ensure only admins can create/update/disable job sources.
- [ ] Validate source base URL.
- [ ] Prevent unapproved source scraping.
- [ ] Add audit logging for source management.

### Scraper Framework
- [ ] Implement scraper service interface.
- [ ] Implement at least one approved source adapter or mock adapter for coursework.
- [ ] Add adapter for JobStreet if feasible.
- [ ] Add adapter for MyCareersFuture if feasible.
- [ ] If real scraping is not feasible, implement seeded/mock scraper with the same data model and logs.
- [ ] Respect source allowlist.
- [ ] Handle network failures safely.
- [ ] Add retry policy with limits.
- [ ] Add timeout for scraping requests.

### Job Normalization and Validation
- [ ] Normalize job fields: title, company, location, category, description, source, posting date, application link.
- [ ] Validate required fields: title, company, source, application link.
- [ ] Validate job URLs.
- [ ] Store source attribution.
- [ ] Store scraped timestamp.
- [ ] Implement content hash.
- [ ] Implement duplicate detection using source ID, external job ID, normalized fields, and/or content hash.
- [ ] Flag malformed jobs.
- [ ] Flag suspicious jobs.

### Scraping Runs
- [ ] Implement scraping run records.
- [ ] Track started time, completed time, source, status, jobs retrieved, and safe error message.
- [ ] Implement weekly scheduled scraping task.
- [ ] Add manual trigger for admin if needed.
- [ ] Add admin view/API for scraping success/failure and jobs retrieved.
- [ ] Add audit logging for scraping failures and admin-triggered scraping.

### Tests
- [ ] Add tests for job normalization.
- [ ] Add tests for duplicate detection.
- [ ] Add tests for suspicious job flagging.
- [ ] Add tests for source allowlist enforcement.
- [ ] Add tests for scraper failure handling.

---

## Phase 6: Job Browsing and Saved Jobs

### Job Search API
- [ ] Implement `GET /jobs` with keyword filter.
- [ ] Implement company filter.
- [ ] Implement location filter.
- [ ] Implement category filter.
- [ ] Implement active-only filtering by default.
- [ ] Add pagination.
- [ ] Add query size limits.
- [ ] Prevent expensive unbounded queries.
- [ ] Use ORM/parameterized queries only.

### Job Detail API
- [ ] Implement `GET /jobs/{job_id}`.
- [ ] Sanitize/encode job descriptions for display.
- [ ] Do not render untrusted HTML unsafely.
- [ ] Validate external job URLs against approved source domains.
- [ ] Add external link warning behaviour.
- [ ] Hide or mark suspicious/inactive jobs appropriately.

### Saved Jobs
- [ ] Implement save job endpoint.
- [ ] Implement unsave job endpoint.
- [ ] Implement list saved jobs endpoint.
- [ ] Ensure users can only view and manage their own saved jobs.
- [ ] Add audit logging for saved job changes if required.

### Frontend
- [ ] Build frontend job listing page.
- [ ] Build frontend job filter/search UI.
- [ ] Build frontend job detail page.
- [ ] Build frontend saved jobs page.
- [ ] Add external link warning UI.
- [ ] Add safe display for job descriptions.

### Tests
- [ ] Add tests for job search.
- [ ] Add tests for filters.
- [ ] Add tests for pagination.
- [ ] Add tests for job detail.
- [ ] Add tests for saved jobs access control.
- [ ] Add tests for XSS payloads in job descriptions.

---

## Phase 7: Secure Resume Upload and Extraction

### Secure Storage
- [ ] Implement protected resume storage directory outside public web root.
- [ ] Ensure storage path is configurable.
- [ ] Ensure storage directory is not served by Nginx.
- [ ] Generate randomized stored filename.
- [ ] Store original filename only as metadata.
- [ ] Store file hash.
- [ ] Prevent path traversal.

### Upload Validation
- [ ] Implement file allowlist for PDF and DOCX.
- [ ] Implement file extension validation.
- [ ] Implement MIME validation.
- [ ] Implement basic file signature/content validation.
- [ ] Implement file size limit.
- [ ] Reject empty files.
- [ ] Reject unsupported files with safe error message.
- [ ] Add rate limiting for upload endpoint.

### Upload API
- [ ] Create resume upload endpoint.
- [ ] Create resume list endpoint.
- [ ] Create resume detail endpoint.
- [ ] Create resume delete endpoint if required.
- [ ] Enforce resume ownership on all resume endpoints.
- [ ] Add audit logging for upload success/failure.

### Extraction Worker
- [ ] Enqueue extraction task after upload.
- [ ] Implement worker task for resume parsing.
- [ ] Add parser timeout.
- [ ] Add memory/resource safeguards where practical.
- [ ] Handle parser failure safely.
- [ ] Store extracted skills, education, experience, and years of experience.
- [ ] Store processing status.
- [ ] Add audit logging for extraction success/failure.
- [ ] Ensure full resume content is not written to ordinary logs.

### Profile Review
- [ ] Allow user to view extracted profile.
- [ ] Allow user to edit extracted profile.
- [ ] Validate edited profile fields.
- [ ] Add audit logging for profile edits.

### Frontend
- [ ] Build frontend resume upload page.
- [ ] Build frontend upload status page or component.
- [ ] Build frontend extracted profile review page.
- [ ] Build frontend extracted profile edit page.

### Tests
- [ ] Add tests for valid PDF upload.
- [ ] Add tests for valid DOCX upload.
- [ ] Add tests for invalid file extension rejection.
- [ ] Add tests for invalid MIME rejection.
- [ ] Add tests for oversized file rejection.
- [ ] Add tests for path traversal filename rejection.
- [ ] Add tests for unauthorized resume access.
- [ ] Add tests for extraction failure handling.

---

## Phase 8: Recommendations

### Recommendation Engine
- [ ] Implement recommendation scoring service.
- [ ] Use extracted skills, experience, education, and job fields.
- [ ] Add simple baseline matching first, then improve if time permits.
- [ ] Store match score.
- [ ] Store recommendation rationale.
- [ ] Ensure recommendation belongs to the requesting user.
- [ ] Avoid leaking other users' profile data.

### Recommendation API
- [ ] Implement recommendation refresh endpoint.
- [ ] Implement list recommendations endpoint.
- [ ] Rate limit recommendation refresh.
- [ ] Enqueue long-running recommendation generation if needed.
- [ ] Add audit logging for recommendation generation.

### Frontend
- [ ] Build frontend recommendations page.
- [ ] Add refresh recommendation action.
- [ ] Show match score and rationale safely.
- [ ] Add empty state if no resume/profile exists.

### Tests
- [ ] Add tests for recommendation generation.
- [ ] Add tests for recommendation ownership.
- [ ] Add tests for refresh after profile update.
- [ ] Add tests for rate-limited refresh if feasible.

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
- [ ] Require admin role for all admin endpoints.
- [ ] Add stronger admin authentication policy if feasible.
- [ ] Add audit logging for every admin action.
- [ ] Add tests proving normal users cannot access admin routes.

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
- [ ] Implement scraping run list.
- [ ] Implement scraping run detail.
- [ ] Show successful runs, failed runs, and jobs retrieved.
- [ ] Show safe error messages only.

### Audit Logs and Health
- [ ] Implement audit log viewer.
- [ ] Add filtering by event type, user, date, and outcome if feasible.
- [ ] Implement service health/monitoring endpoint.
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
- [ ] Add tests for admin-only endpoints.
- [ ] Add tests for admin job disable/enable.
- [ ] Add tests for admin audit log access.
- [ ] Add tests that admin actions create audit logs.

---

## Phase 12: Security Hardening

### Input/Output Security
- [ ] Add global input validation and schema validation.
- [ ] Add output encoding/sanitization strategy.
- [ ] Add HTML sanitizer if rich job descriptions are displayed.
- [ ] Add tests for XSS payloads.
- [ ] Add tests for SQL injection attempts.

### HTTP and Browser Security
- [ ] Add security headers in Nginx.
- [ ] Add Content Security Policy.
- [ ] Add `X-Content-Type-Options: nosniff`.
- [ ] Add `Referrer-Policy`.
- [ ] Add frame protection via CSP or `X-Frame-Options`.
- [ ] Add request size limits.
- [ ] Ensure HTTPS/TLS is configured for deployment.

### Production Safety
- [ ] Ensure debug mode is disabled in production.
- [ ] Ensure frontend does not expose secrets.
- [ ] Ensure backend does not return internal errors.
- [ ] Ensure Redis is not exposed publicly.
- [ ] Ensure PostgreSQL is not exposed publicly.
- [ ] Ensure uploaded files are not exposed publicly.
- [ ] Ensure logs/backups are not in public directories.

### Logging and Sensitive Data
- [ ] Ensure logs do not contain passwords.
- [ ] Ensure logs do not contain reset tokens.
- [ ] Ensure logs do not contain session tokens.
- [ ] Ensure logs do not contain API keys.
- [ ] Ensure logs do not contain full resume content.
- [ ] Ensure logs do not contain full AI prompts with personal data.
- [ ] Add log redaction helper if needed.

### Availability and Abuse Protection
- [ ] Add rate limiting to login, reset, upload, recommendation, and cover letter endpoints.
- [ ] Add account lockout or progressive delay after repeated failed login attempts.
- [ ] Add upload size limits at Nginx and backend.
- [ ] Add worker task timeouts.
- [ ] Add queue limits or backpressure if feasible.
- [ ] Add pagination limits for list endpoints.

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
- [ ] Add backend unit tests for auth.
- [ ] Add backend unit tests for password hashing.
- [ ] Add backend unit tests for reset token hashing/expiry.
- [ ] Add backend unit tests for authorization helpers.
- [ ] Add backend unit tests for file validation.
- [ ] Add backend unit tests for job normalization.
- [ ] Add backend unit tests for duplicate detection.
- [ ] Add backend unit tests for recommendation scoring.
- [ ] Add backend unit tests for AI prompt builder.
- [ ] Add backend unit tests for audit logging helper.

### Backend Integration Tests
- [ ] Add integration tests for account CRUD.
- [ ] Add integration tests for login/logout/session expiry.
- [ ] Add integration tests for password reset.
- [ ] Add integration tests for resume upload and extraction task.
- [ ] Add integration tests for job search and saved jobs.
- [ ] Add integration tests for recommendation generation.
- [ ] Add integration tests for cover letter generation flow.
- [ ] Add integration tests for application history.
- [ ] Add integration tests for admin controls.

### Security Tests
- [ ] Add security tests for broken access control.
- [ ] Add security tests for invalid file uploads.
- [ ] Add security tests for path traversal upload filenames.
- [ ] Add security tests for generic login/reset errors.
- [ ] Add security tests for SQL injection attempts.
- [ ] Add security tests for XSS payloads in job descriptions/profile fields.
- [ ] Add security tests for unauthorized admin access.
- [ ] Add security tests checking sensitive values are not logged.

### Frontend Tests
- [ ] Add frontend lint.
- [ ] Add frontend type check.
- [ ] Add frontend build test.
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
