## Project Name
Secure AI-Assisted Job Aggregation and Application Support Platform

## Purpose of this File
This file gives Codex and other coding agents the repository-level instructions needed to build this application safely and consistently.

Security is not optional. Every feature must be implemented with authentication, authorization, input validation, output encoding, audit logging, and least privilege in mind.

Codex must treat this file as the main instruction file for the repository.

---

## Product Summary
Build a secure web application that:
- Aggregates job postings weekly from approved Singapore job portals such as JobStreet and MyCareersFuture.
- Stores normalized job records in PostgreSQL.
- Allows users to browse, search, filter, save, and view job postings.
- Allows authenticated users to upload resumes in approved formats.
- Extracts structured resume information such as skills, education, work history, and years of experience.
- Generates ranked job recommendations from the extracted user profile and stored job postings.
- Generates editable draft cover letters for selected jobs.
- Lets users view application preparation history.
- Provides administrators with scraping status, user management, job moderation, audit logs, and monitoring.

The application handles sensitive user data, external scraped data, uploaded files, AI-generated output, and scheduled background tasks. Therefore, all implementation must follow secure software development principles.

---

## Expected Tech Stack
Use this stack unless explicitly changed by the user:

- Frontend: Next.js + React + TypeScript + Tailwind CSS
- Backend API: FastAPI + Python
- Database: PostgreSQL
- Queue/cache: Redis
- Background jobs: Celery or RQ
- Reverse proxy/deployment: Nginx + Docker Compose on the provided AWS VM
- Security tooling: Semgrep, Bandit, Gitleaks, Trivy, dependency scanners
- Testing: pytest for backend, frontend unit tests, integration/security tests for critical flows

---

## Repository Structure
Prefer this structure:

```text
/
├── AGENTS.md
├── PRD.md
├── ARCHITECTURE.md
├── TASKS.md
├── CODING_GUIDELINES.md
├── README.md
├── docker-compose.yml
├── .env.example
├── frontend/
│   ├── package.json
│   ├── src/
│   │   ├── app/
│   │   ├── components/
│   │   ├── lib/
│   │   └── styles/
├── backend/
│   ├── pyproject.toml
│   ├── alembic/
│   ├── app/
│   │   ├── main.py
│   │   ├── core/
│   │   ├── api/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── services/
│   │   ├── workers/
│   │   ├── security/
│   │   └── tests/
├── infra/
│   ├── nginx/
│   ├── scripts/
│   └── ci/
└── docs/
```

---

## Required Supporting Markdown Files
This repository should also contain:

- `PRD.md` — product requirements, FR/NFR/SFR/FSR/NFSR/SDR.
- `ARCHITECTURE.md` — physical architecture, logical architecture, Level 0 DFD, database schema.
- `TASKS.md` — phased implementation checklist.
- `CODING_GUIDELINES.md` — detailed coding, security, testing, and deployment rules.

Codex should consult these files before making implementation decisions.

---

## Implementation Priority
Implement in this order:

1. Project skeleton, Docker Compose, environment configuration.
2. Database models and migrations.
3. Authentication, session management, password hashing, and RBAC.
4. Account CRUD and profile management.
5. Job source model, scraping run tracking, job posting model, duplicate detection.
6. Job browsing/search/detail APIs and frontend pages.
7. Resume upload, secure file storage, and worker-based extraction.
8. Recommendation generation.
9. Cover letter draft generation and editing.
10. Saved jobs and application history.
11. Admin dashboard for users, jobs, scraping runs, monitoring, and audit logs.
12. Security hardening, testing, CI security checks, and deployment scripts.

Do not jump directly to AI features before authentication, authorization, and core data protection are implemented.

---

## Main Functional Areas

### Account and Authentication
Implement:
- Registration
- Login
- Logout
- Password change
- Password reset
- Profile view
- Profile update
- Account deletion with re-authentication

Security must include:
- Strong password hashing
- Secure sessions
- Rate limiting
- Generic error messages
- Audit logging
- Backend authorization checks

### Job Aggregation and Search
Implement:
- Approved job source configuration
- Weekly scraping
- Job normalization
- Duplicate detection
- Suspicious/malformed job flagging
- Search and filtering
- Job detail viewing
- Redirect to original source

Security must include:
- Source allowlist
- Input validation
- Output encoding
- URL/domain validation
- Scraping run audit logs

### Resume Upload and Processing
Implement:
- Resume upload
- Resume update/replacement
- Protected file storage
- Resume extraction
- Editable extracted profile

Security must include:
- Approved file type allowlist
- MIME/content validation
- File size limit
- Randomized filename
- Storage outside public web root
- Worker-based parsing
- No full resume contents in logs

### Recommendation and Cover Letter
Implement:
- Recommendation generation
- Recommendation refresh
- Cover letter draft generation
- Cover letter editing
- Application preparation history

Security must include:
- AI prompt separation
- Data minimization
- Rate limiting
- Draft-only generation
- No automatic external submission
- Audit logging

### Administration
Implement:
- Admin user management
- Job review/moderation
- Scraping run monitoring
- Audit log viewing
- Platform health monitoring

Security must include:
- Admin-only RBAC
- Stronger admin protection
- Audit logging for every admin action
- No silent data changes

---

## Security Rules Codex Must Follow

### 1. Authentication and Passwords
- Never store plaintext passwords.
- Use Argon2id or bcrypt with secure parameters.
- Use secure, random session tokens.
- If using cookie-based sessions, cookies must be:
  - `HttpOnly`
  - `Secure` in production
  - `SameSite=Lax` or `SameSite=Strict`
- Store session tokens hashed in the database if server-side sessions are used.
- Password reset tokens must be:
  - random
  - single-use
  - time-limited
  - stored hashed
  - invalidated after use
- Use generic errors for login and password reset.
- Do not reveal whether an email exists.

### 2. Authorization and RBAC
- Enforce authorization in backend endpoints.
- Do not rely on frontend route hiding.
- Normal users can only access their own:
  - account profile
  - uploaded resumes
  - extracted profile data
  - saved jobs
  - recommendations
  - cover letters
  - application history
- Admin routes must require role `ADMIN`.
- Admin activity must be logged.
- Failed authorization attempts must be logged.

Use backend helpers such as:
- `require_authenticated_user`
- `require_admin`
- `assert_owner_or_admin`

### 3. Input Validation
Validate all:
- request bodies
- query parameters
- path parameters
- uploaded files
- scraped job data
- AI-related inputs
- admin inputs

Use:
- Pydantic schemas
- enum allowlists
- length limits
- type validation
- pagination limits
- strict file validation

### 4. Output Encoding and XSS Protection
Treat the following as untrusted:
- scraped job descriptions
- company names
- job titles
- user profile fields
- uploaded resume extracted text
- AI-generated cover letters

Do not use unsafe HTML rendering unless sanitized.

Add:
- output encoding
- sanitization where required
- Content Security Policy through Nginx or frontend headers

### 5. Database Safety
- Use SQLAlchemy ORM or parameterized queries only.
- Never concatenate raw SQL using user input.
- Use foreign keys and constraints.
- Use transactions for multi-step account and data updates.
- Prevent partial or corrupted records.
- Use least-privilege database credentials.

### 6. File Upload Safety
Uploaded resumes are high-risk.

Only allow approved formats:
- PDF
- DOCX

Validate:
- extension
- MIME type
- file signature or content structure
- file size
- filename safety

Storage rules:
- Store outside public web root.
- Use randomized stored filenames.
- Store original filename only as metadata.
- Store file hash.
- Prevent path traversal.
- Do not serve uploaded files directly from Nginx public directory.

Processing rules:
- Parse resumes in a background worker.
- Use timeouts.
- Handle malformed files safely.
- Log upload status, not full content.

### 7. Scraping Safety
- Scrape only approved/configured sources.
- Treat all scraped data as untrusted.
- Normalize data before storage.
- Required job fields:
  - title
  - company
  - source
  - application link
- Detect duplicates using source ID, external job ID, normalized fields, or content hash.
- Mark suspicious/malformed jobs before display.
- Validate external application links.
- Add external link warning where useful.
- Log scraping success/failure.

### 8. AI Safety
- Treat resume text and job descriptions as untrusted prompt content.
- Keep trusted system instructions separate from untrusted content.
- Delimit untrusted content clearly.
- Limit prompt size.
- Send only the data needed for the specific AI task.
- Avoid sending full raw resume content unless absolutely necessary.
- AI-generated cover letters are drafts only.
- Never auto-submit cover letters to external job platforms.
- Rate limit AI generation endpoints.
- Log generation metadata, not full sensitive prompts.

### 9. Logging and Audit Trail
Log security-relevant events:
- registration attempts
- login success/failure
- logout
- password change
- password reset request and completion
- profile update
- account deletion
- failed authorization attempts
- resume upload success/failure
- resume extraction success/failure
- recommendation generation
- cover letter generation/editing
- saved job changes
- admin actions
- scraping run success/failure
- suspicious job flagging

Each audit log should include:
- timestamp
- user ID if available
- event type
- target type
- target ID
- IP address if available
- user agent if available
- outcome
- safe details

Never log:
- plaintext passwords
- password reset tokens
- session tokens
- API keys
- private keys
- full resume contents
- full AI prompts containing personal data
- sensitive environment variables

### 10. Error Handling
- Fail securely.
- Return generic user-facing errors.
- Do not expose:
  - stack traces
  - framework debug pages
  - internal file paths
  - SQL errors
  - config values
  - secrets
- Log internal error details safely for debugging.

### 11. Rate Limiting
Apply rate limits to:
- registration
- login
- password reset
- resume upload
- recommendation refresh
- cover letter generation
- search endpoints if abused
- admin login if implemented separately

Consider account lockout or progressive delay after repeated failed login attempts.

### 12. Secure Configuration
- Use `.env.example` only for placeholder names.
- Never commit `.env`.
- Never hardcode:
  - database credentials
  - API keys
  - session secrets
  - private keys
  - email credentials
- Disable debug mode in production.
- Use environment variables or protected deployment secrets.
- Separate development, testing, and production config.

### 13. Secure Backups
- Back up PostgreSQL data.
- Back up protected resume storage if needed.
- Back up audit logs.
- Protect backups from unauthorized access.
- Do not store backups in public directories.
- Test restore process.

### 14. Secure Development Pipeline
Add checks where possible:
- backend tests
- frontend lint/build
- Bandit or Semgrep
- dependency vulnerability scanning
- Gitleaks secret scanning
- Trivy container scanning

CI should fail on:
- failing tests
- committed secrets
- severe dependency vulnerabilities
- unsafe lint/type errors
- insecure code patterns where practical

---

## Threats Codex Must Design Against

The implementation must address these risks:

1. Data leakage of resumes, profiles, generated cover letters, and application history.
2. Account takeover through brute force, credential stuffing, or password reset abuse.
3. Broken access control and privilege escalation.
4. Malicious resume upload.
5. Job data poisoning through scraped content.
6. Stored/reflected XSS from job descriptions or profile content.
7. Malicious redirect to phishing job sources.
8. Prompt injection and AI misuse.
9. Denial of service/resource exhaustion.
10. Log tampering or sensitive data exposure in logs.
11. Hardcoded secrets and vulnerable dependencies.
12. Backup exposure or recovery failure.
13. Scraping failure or stale job data.
14. Misleading AI-generated recommendations or cover letters.

---

## API Design Rules

### Auth APIs
Expected routes:
- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/logout`
- `POST /auth/password-change`
- `POST /auth/password-reset/request`
- `POST /auth/password-reset/confirm`

### Account/Profile APIs
Expected routes:
- `GET /me`
- `PATCH /me`
- `DELETE /me`
- `GET /me/profile`
- `PATCH /me/profile`

### Resume APIs
Expected routes:
- `POST /resumes`
- `GET /resumes`
- `GET /resumes/{resume_id}`
- `DELETE /resumes/{resume_id}`
- `GET /resumes/{resume_id}/extraction`

### Job APIs
Expected routes:
- `GET /jobs`
- `GET /jobs/{job_id}`
- `POST /jobs/{job_id}/save`
- `DELETE /jobs/{job_id}/save`
- `GET /saved-jobs`

### Recommendation APIs
Expected routes:
- `POST /recommendations/refresh`
- `GET /recommendations`

### Cover Letter APIs
Expected routes:
- `POST /jobs/{job_id}/cover-letter`
- `GET /cover-letters`
- `GET /cover-letters/{cover_letter_id}`
- `PATCH /cover-letters/{cover_letter_id}`

### Application History APIs
Expected routes:
- `GET /application-history`

### Admin APIs
Expected routes:
- `GET /admin/users`
- `PATCH /admin/users/{user_id}`
- `GET /admin/jobs`
- `PATCH /admin/jobs/{job_id}`
- `GET /admin/scraping-runs`
- `GET /admin/audit-logs`
- `GET /admin/health`

---

## Database Requirements

Use PostgreSQL with SQLAlchemy and Alembic.

Required tables:
- `users`
- `sessions`
- `password_reset_tokens`
- `user_profiles`
- `resumes`
- `resume_extractions`
- `job_sources`
- `scraping_runs`
- `job_postings`
- `saved_jobs`
- `recommendations`
- `cover_letters`
- `application_history`
- `audit_logs`

Database rules:
- Add primary keys.
- Add foreign keys.
- Add indexes where needed.
- Add unique constraints where needed.
- Use `created_at` and `updated_at` fields where useful.
- Use `ON DELETE` behaviour intentionally.
- Do not store raw session tokens or raw password reset tokens.
- Do not store plaintext passwords.

---

## Testing Requirements

Write tests for:

### Authentication
- successful registration
- duplicate registration
- successful login
- failed login
- generic login error
- logout invalidates session
- password change
- password reset request
- password reset confirm
- expired reset token
- reused reset token

### Authorization
- user cannot view another user profile
- user cannot update another user profile
- user cannot access another user's resume
- user cannot access another user's saved jobs
- user cannot access another user's cover letters
- user cannot access admin routes
- admin can access admin routes

### File Upload
- valid PDF upload
- valid DOCX upload
- invalid extension rejected
- invalid MIME rejected
- oversized file rejected
- path traversal filename rejected
- parsing failure handled safely

### Jobs
- job search works
- filters work
- pagination works
- duplicate job detection works
- suspicious job flagging works
- malicious HTML is sanitized/encoded

### AI Features
- recommendation generation works
- cover letter draft generation works
- cover letter editing works
- generated cover letter belongs to correct user
- rate limiting applies

### Audit Logs
- login events are logged
- upload events are logged
- admin actions are logged
- failed authorization is logged
- sensitive values are not logged

### Security
- SQL injection attempts do not alter queries
- XSS payloads are not rendered unsafely
- unauthorized object access is blocked
- generic errors do not leak internals

Minimum target:
- At least 70% unit test coverage for critical backend modules.

---

## Frontend Rules

Frontend must include:
- register page
- login page
- password reset pages
- account/profile page
- resume upload page
- extracted profile review/edit page
- job search/list page
- job detail page
- saved jobs page
- recommendations page
- cover letter draft page
- application history page
- admin dashboard

Frontend must not:
- store secrets
- store session tokens in localStorage
- rely on client-only authorization
- render untrusted HTML unsafely
- expose stack traces or raw backend errors

---

## Deployment Rules

Deployment target:
- Provided AWS VM.
- Web frontend must be served from the provided AWS VM.

Use:
- Docker Compose
- Nginx reverse proxy
- PostgreSQL internal container/service
- Redis internal container/service
- Worker container/service

Expose publicly:
- 80/443 for web traffic
- 22 for SSH, restricted where possible

Do not expose publicly:
- PostgreSQL
- Redis
- internal backend ports unless routed safely through Nginx
- resume storage
- logs
- backups

Production rules:
- Debug mode disabled.
- Secure cookies enabled.
- HTTPS/TLS enabled.
- Environment variables configured on VM.
- No real secrets committed to GitHub.
- Health checks configured.
- Backups scheduled.
- Logs retained.

---

## Definition of Done

A feature is done only when:

- Backend validation exists.
- Backend authorization checks exist.
- Authentication is required where appropriate.
- RBAC or ownership checks are applied.
- Security-relevant actions are audit logged.
- Sensitive data is not logged.
- User-facing errors are safe and generic.
- Database operations are safe and transactional where needed.
- Tests cover success and failure cases.
- The frontend handles errors safely.
- Documentation or task files are updated if architecture/behaviour changes.
- No secrets are committed.
- The implementation follows `PRD.md`, `ARCHITECTURE.md`, `TASKS.md`, and `CODING_GUIDELINES.md`.

---

## Codex Working Instructions

When working on this repository:

1. Read this file first.
2. Read `PRD.md`, `ARCHITECTURE.md`, `TASKS.md`, and `CODING_GUIDELINES.md` before large changes.
3. Prefer small, focused commits/patches.
4. Do not remove security checks to make tests pass.
5. Do not introduce insecure shortcuts.
6. Do not hardcode secrets.
7. Do not skip authorization checks.
8. Do not return raw database models from APIs.
9. Do not expose internal error details to users.
10. If a feature touches sensitive data, add audit logging.
11. If a feature creates a new endpoint, add validation and tests.
12. If a feature creates a new user-owned resource, add ownership checks.
13. If a feature accepts files, apply upload validation.
14. If a feature displays external or user-generated content, sanitize or encode it.
15. If unsure, choose the safer fail-closed implementation.

---

## When Unsure
Choose the safer implementation.

Prefer:
- allowlists over blocklists
- backend enforcement over frontend-only checks
- secure defaults over optional security
- least privilege over broad access
- generic errors over detailed errors
- explicit validation over implicit trust
- auditability over silent changes
- fail-closed behaviour over fail-open behaviour
