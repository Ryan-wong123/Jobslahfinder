# Coding Guidelines

## 1. Purpose
This document defines the coding, security, testing, deployment, and review standards for the Secure AI-Assisted Job Aggregation and Application Support Platform.

The project handles sensitive account data, uploaded resumes, extracted profile data, saved jobs, generated cover letters, audit logs, external scraped data, and AI-generated output. Therefore, security must be treated as a core development requirement, not an afterthought.

These guidelines are intended for human developers and coding agents such as Codex.

---

## 2. Core Principles
All code must follow these principles:

- Secure by default.
- Least privilege.
- Defense in depth.
- Fail securely.
- Validate input and encode output.
- Do not trust frontend, external job sources, uploaded files, or AI outputs.
- Do not expose sensitive internal details to users.
- Keep modules small and maintainable.
- Write tests for critical logic.
- Prefer allowlists over blocklists.
- Prefer backend enforcement over frontend-only checks.
- Prefer explicit validation over implicit trust.
- Prefer fail-closed behavior over fail-open behavior.

---

## 3. Project Technology Baseline
Use this baseline unless explicitly changed:

- Frontend: Next.js, React, TypeScript, Tailwind CSS
- Backend: FastAPI, Python 3.11+
- Database: PostgreSQL
- ORM/Migrations: SQLAlchemy + Alembic
- Queue/Cache: Redis
- Background Jobs: Celery or RQ
- Reverse Proxy: Nginx
- Deployment: Docker Compose on the provided AWS VM
- Testing: pytest for backend, frontend tests where appropriate
- Security Tooling: Semgrep, Bandit, Gitleaks, Trivy, dependency scanners

---

## 4. Repository Organization
Prefer this structure:

```text
/
|-- AGENTS.md
|-- README.md
|-- docker-compose.yml
|-- .env.example
|-- docs/
|   |-- PRD.md
|   |-- ARCHITECTURE.md
|   |-- TASKS.md
|   |-- CODING_GUIDELINES.md
|   |-- DEPLOYMENT.md
|   |-- DEPLOYMENT_COMMANDS.md
|   `-- prompts.md
|-- frontend/
|   |-- package.json
|   `-- src/
|       |-- app/
|       |-- components/
|       |-- lib/
|       `-- styles/
|-- backend/
|   |-- pyproject.toml
|   |-- alembic/
|   `-- app/
|       |-- main.py
|       |-- core/
|       |-- api/
|       |-- models/
|       |-- schemas/
|       |-- services/
|       |-- workers/
|       |-- security/
|       `-- tests/
`-- infra/
    |-- nginx/
    |-- scripts/
    `-- ci/
```

---

## 5. Python / FastAPI Backend Guidelines

### 5.1 Style

- Use Python 3.11+.
- Use type hints for all public functions.
- Prefer small service modules over large route files.
- Keep route handlers thin.
- Put business logic in `services/`.
- Put security helpers in `security/`.
- Put database models in `models/`.
- Put Pydantic schemas in `schemas/`.
- Put background jobs in `workers/`.
- Put shared configuration in `core/config.py`.
- Put database session setup in `core/database.py`.
- Put audit/security logging helpers in a dedicated module.

### 5.2 Example Backend Structure

```text
backend/app/
├── main.py
├── core/
│   ├── config.py
│   ├── database.py
│   ├── logging.py
│   └── rate_limit.py
├── api/
│   ├── auth.py
│   ├── users.py
│   ├── resumes.py
│   ├── jobs.py
│   ├── recommendations.py
│   ├── cover_letters.py
│   └── admin.py
├── models/
├── schemas/
├── services/
├── security/
└── workers/
```

### 5.3 FastAPI Rules

- Use Pydantic models for all request and response schemas.
- Do not return SQLAlchemy models directly from routes.
- Use explicit response models.
- Use dependency injection for database sessions, current user, and admin checks.
- Use appropriate HTTP status codes.
- Return safe, consistent, generic error messages.
- Add rate limiting to sensitive endpoints.
- Never trust path parameters or query parameters without validation.
- Avoid putting complex logic directly inside route handlers.

### 5.4 Backend Module Separation

Use this responsibility split:

| Module | Responsibility |
|---|---|
| `api/` | Request routing and response shaping |
| `schemas/` | Pydantic validation and response models |
| `models/` | SQLAlchemy table models |
| `services/` | Business logic |
| `security/` | Passwords, sessions, auth dependencies, RBAC, tokens |
| `workers/` | Celery/RQ tasks for scraping, parsing, recommendation, AI |
| `core/` | Config, database, logging, app startup |
| `tests/` | Unit, integration, and security tests |

---

### 5.5 Salary Normalization and Experience Comparison

Salary comparison uses the midpoint of a complete advertised salary range. Only SGD records are currently comparable. Monthly values use a factor of 1; annual values are divided by 12; weekly values are multiplied by 52/12; daily values assume 260 paid working days per year and are multiplied by 260/12; and hourly values assume 173.33 paid hours per month. Records with missing or inverted bounds, unsupported currency or period, or implausible normalized values are excluded. These constants and the four experience-band boundaries must remain centralized in the job-role service and covered by unit tests. Median is the primary estimate, and at least five qualifying postings are required before an estimate may be displayed.

## 6. Frontend Guidelines

### 6.1 Stack

- Use Next.js with React and TypeScript.
- Use Tailwind CSS for styling.
- Prefer reusable components.
- Keep API functions in `frontend/src/lib/`.
- Keep pages/routes in `frontend/src/app/`.
- Keep UI components in `frontend/src/components/`.

### 6.2 Frontend Security

- Do not store secrets in frontend code.
- Do not store session tokens in `localStorage` or `sessionStorage`.
- Prefer HttpOnly cookie-based sessions.
- Treat all displayed job descriptions, AI output, and user profile content as untrusted.
- Avoid `dangerouslySetInnerHTML`.
- If rendering HTML is unavoidable, sanitize first.
- Frontend role checks are for user experience only; backend must enforce all authorization.
- Never expose raw backend errors, stack traces, SQL errors, or internal paths to users.

### 6.3 Required UI Pages

Implement these pages/components:

- Register
- Login
- Logout action
- Forgot password
- Reset password
- Account/profile view and edit
- Change password
- Delete account with re-authentication
- Job search/list
- Job detail
- Saved jobs
- Resume upload
- Extracted profile review/edit
- Recommendations
- Cover letter draft generation and editing
- Application history
- Admin dashboard
- Scraping run monitoring
- Audit log viewer

### 6.4 UI Error Handling

- Use safe user-facing messages.
- Do not show exception details.
- For login, use generic messages such as `Invalid email or password`.
- For password reset, do not reveal whether an email exists.
- For upload errors, explain allowed file types and size limits without exposing parser internals.

---

## 7. Authentication Guidelines

### 7.1 Password Storage

- Never store plaintext passwords.
- Use Argon2id or bcrypt with secure parameters.
- Use per-password salts handled by the hashing library.
- Do not implement custom password hashing.
- Do not log passwords.

### 7.2 Login

- Use generic failure messages.
- Rate limit failed login attempts.
- Consider account lockout or progressive delay after repeated failed attempts.
- Audit both successful and failed logins.
- Store last login timestamp where useful.

### 7.3 Sessions

- Session tokens must be random and hard to guess.
- If server-side sessions are used, store only a hash of the session token in the database.
- Expire sessions after inactivity.
- Invalidate session on logout.
- Invalidate sessions after password change where appropriate.
- Use secure cookies:
  - `HttpOnly`
  - `Secure` in production
  - `SameSite=Lax` or `SameSite=Strict`

### 7.4 Password Reset

Password reset tokens must be:

- random
- single-use
- time-limited
- stored hashed
- invalidated after successful use

Password reset request must not reveal whether the email exists.

### 7.5 Password Change

- Require current password before password change.
- Audit password change attempts.
- Invalidate active sessions if the security design requires it.

### 7.6 Account Deletion

- Require re-authentication or equivalent verification before account deletion.
- Use a transaction for account deletion and related data updates.
- Log account deletion.
- Do not allow users to delete other users.

---

## 8. Authorization and RBAC Guidelines

### 8.1 Roles

Minimum roles:

- `USER`
- `ADMIN`

### 8.2 Rules

- Every protected route must require authentication.
- Admin routes must require the `ADMIN` role.
- Every user-owned resource must check ownership.
- Do not rely on frontend hiding.
- Access control failures must be logged.
- Backend must reject unauthorized access even if a user guesses an ID.

### 8.3 Ownership-Protected Resources

Users can access only their own:

- account profile
- uploaded resumes
- extracted resume data
- saved jobs
- recommendations
- generated cover letters
- application history

Admins can access admin functions only through admin routes, and admin access must be audited.

### 8.4 Recommended Helpers

Create helpers such as:

- `require_authenticated_user`
- `require_admin`
- `assert_owner_or_admin`
- `get_owned_resource_or_404`

Use `404 Not Found` rather than `403 Forbidden` where revealing resource existence is risky.

---

## 9. Input Validation Guidelines

Validate all input:

- request bodies
- query parameters
- path parameters
- headers where relevant
- uploaded files
- scraped job data
- AI-related inputs
- admin form inputs

Use:

- Pydantic schemas
- enum allowlists
- min/max length limits
- numeric range checks
- pagination limits
- strict date parsing
- strict URL validation
- file validation

Implementation rules:

- Prefer one shared backend text validation helper for trimming, Unicode normalization, control-character handling, length limits, and optional HTML rejection.
- Validate password reset tokens with an allowlist pattern matching the generated token format, not length alone.
- Validate all public query flags that can reveal moderated or inactive content; suspicious/inactive job filters must remain admin-only.
- Use positive path parameter constraints consistently for all resource IDs, including admin IDs.
- Use explicit response schemas for AI-generated structured output such as interview questions.
- Reject overlong list items rather than silently truncating security-relevant user input.

Do not rely on frontend validation only.

---

## 10. Output Encoding and XSS Protection

Treat these as untrusted:

- scraped job titles
- scraped company names
- scraped job descriptions
- user profile fields
- extracted resume text
- generated cover letters
- admin-entered notes or flags

Controls:

- Encode output in the correct context.
- Sanitize HTML if HTML must be rendered.
- Avoid unsafe raw HTML rendering.
- Add a Content Security Policy.
- Escape user-controlled values in templates and UI components.
- Do not treat scraped content as safe just because it came from a known job portal.

---

## 11. Database Guidelines

### 11.1 Query Safety

- Use SQLAlchemy ORM or parameterized queries only.
- Never concatenate raw SQL using user input.
- Never use f-strings to build SQL with user-controlled values.
- Validate and constrain sorting/filtering fields using allowlists.

### 11.2 Schema Safety

- Use primary keys.
- Use foreign keys.
- Use uniqueness constraints where needed.
- Use indexes for common lookups.
- Use transactions for multi-step updates.
- Use `created_at` and `updated_at` where useful.
- Use `ON DELETE` behavior intentionally.

### 11.3 Sensitive Data Storage

Do not store:

- plaintext passwords
- raw session tokens
- raw password reset tokens
- API keys in normal database tables unless required and encrypted/protected

Store:

- password hashes
- session token hashes
- password reset token hashes
- file hashes
- audit event metadata

### 11.4 Least Privilege

- Use a limited database account for the application.
- Do not use the database superuser for normal app operations.
- Database should not be exposed publicly.

---

## 12. File Upload Guidelines

Uploaded resumes are high-risk input.

### 12.1 Allowed Files

Allow only approved resume formats:

- PDF
- DOCX

Reject unsupported formats.

### 12.2 Validation

Validate:

- file extension
- MIME type
- content-derived MIME or signature match
- basic file signature/content structure
- file size
- filename safety
- path traversal attempts
- archive safety for DOCX files, including maximum entry count, maximum total uncompressed size, and maximum compression ratio

Do not trust the original filename.
Do not trust the client-provided MIME type by itself.

### 12.3 Storage

- Store outside the public web root.
- Use randomized stored filenames.
- Store original filename only as metadata.
- Store file hash.
- Store MIME type and size.
- Do not serve files directly from Nginx static directories.
- Access files only through authorized backend endpoints.

### 12.4 Processing

- Parse files in a background worker.
- Use task timeouts.
- Apply memory/resource limits where practical.
- Handle parser failures safely.
- Do not log full resume contents.
- Log only metadata such as user ID, file hash, upload status, and outcome.
- Never print or log raw extracted resume text, even during debugging.

---

## 13. Scraping and External Job Data Guidelines

### 13.1 Approved Sources

- Scrape only approved and configured job sources.
- Use a source allowlist.
- Store source attribution and scrape timestamp.

### 13.2 Data Normalization

Normalize these fields:

- title
- company
- location
- category
- description
- source
- posting date
- application link

### 13.3 Data Quality

- Reject or flag malformed jobs.
- Detect duplicates using source ID, external job ID, normalized fields, or content hash.
- Mark suspicious jobs before presenting them to users.
- Allow admins to disable or delete invalid or suspicious jobs.

### 13.4 Security

- Treat all scraped content as untrusted.
- Sanitize/encode descriptions before display.
- Validate job URLs against approved source domains where possible.
- Show external link warning when redirecting users.
- Log scraping run success/failure and number of jobs retrieved.

---

## 14. AI Integration Guidelines

AI features include:

- resume extraction support where applicable
- job recommendation support where applicable
- cover letter draft generation

### 14.1 Prompt Safety

- Treat resume text, extracted profile data, and job descriptions as untrusted.
- Keep system instructions separate from untrusted content.
- Wrap untrusted content in clear delimiters.
- Limit prompt size.
- Do not let user/job/resume content override system instructions.

### 14.2 Data Minimization

- Send only data needed for the specific task.
- Avoid sending full raw resume content unless required.
- Avoid sending unnecessary identifiers such as internal user IDs.
- Avoid sending sensitive account data to AI service.

### 14.3 Output Handling

- AI-generated cover letters must be drafts only.
- Users must be able to review and edit generated cover letters.
- Never auto-submit applications to external job platforms.
- Treat AI output as untrusted until safely displayed.
- Store recommendation rationale when useful.
- Validate structured AI responses against explicit schemas before returning or storing them.

### 14.4 Abuse Prevention

- Rate limit recommendation refresh.
- Rate limit cover letter generation.
- Log generation metadata, not full sensitive prompts.
- Handle AI provider failures gracefully.

---

## 15. Logging and Audit Guidelines

### 15.1 Events to Log

Log these security-relevant events:

- registration attempts
- login success/failure
- logout
- password reset request
- password reset completion
- password change
- profile update
- account deletion
- failed authorization attempts
- resume upload success/failure
- resume extraction success/failure
- recommendation generation
- cover letter generation
- cover letter editing
- saved job changes
- admin actions
- scraping run success/failure
- suspicious job flagging
- backup/restore operations where applicable

### 15.2 Audit Log Fields

Each audit log should include:

- timestamp
- user ID where available
- event type
- target type
- target ID
- IP address where available
- user agent where available
- outcome
- safe details

### 15.3 Never Log

Never log:

- plaintext passwords
- password reset tokens
- session tokens
- API keys
- private keys
- full resume contents
- full AI prompts containing personal data
- generated cover letter text
- edited cover letter text
- sensitive environment variables
- raw database credentials

### 15.4 Log Protection

- Restrict access to logs.
- Protect logs from tampering.
- Retain audit logs for at least 90 days if feasible for the coursework deployment.
- Redact sensitive values.
- Apply maximum length limits to nested audit detail strings and user-agent values.
- Use structured logging where possible.

---

## 16. Error Handling Guidelines

- Fail securely.
- Use generic user-facing errors.
- Do not expose stack traces.
- Do not expose framework debug pages.
- Do not expose internal file paths.
- Do not expose SQL errors.
- Do not expose configuration values.
- Do not expose secrets.
- Log internal details safely for developers/admins.

Examples:

| Situation | User-Facing Error |
|---|---|
| Wrong login | `Invalid email or password.` |
| Password reset email not found | `If the account exists, a reset link has been sent.` |
| Unauthorized object access | `Resource not found.` or `Access denied.` |
| Resume parser failure | `We could not process this file. Please upload a supported resume file.` |
| Server exception | `Something went wrong. Please try again later.` |

---

## 17. Rate Limiting Guidelines

Apply rate limits to:

- registration
- login
- password reset request
- password reset confirm
- resume upload
- recommendation refresh
- cover letter generation
- search endpoints if abused
- admin login/admin actions if needed

Consider:

- per-IP limits
- per-account limits
- progressive delay for repeated failed login attempts
- temporary account lockout after repeated failed attempts
- queue limits for background jobs

---

## 18. Secure Configuration and Secret Management

### 18.1 Environment Files

- Keep `.env.example` with placeholder values only.
- Never commit `.env`.
- Never commit real secrets.

### 18.2 Secrets

Never hardcode:

- database passwords
- API keys
- session secrets
- JWT signing secrets if used
- private keys
- email service credentials
- AI service keys

### 18.3 Production Settings

- Disable debug mode in production.
- Use secure cookies in production.
- Use HTTPS/TLS.
- Use different secrets per environment.
- Rotate secrets if exposed.

---

## 19. Backup and Recovery Guidelines

- Back up PostgreSQL data.
- Back up protected resume storage if required.
- Back up audit logs if required.
- Protect backups from unauthorized access.
- Do not store backups in public directories.
- Test restore process.
- Do not include plaintext secrets in backups where avoidable.

---

## 20. Docker and Deployment Guidelines

### 20.1 Docker

- Use Docker Compose.
- Run services as non-root where practical.
- Use internal Docker networks.
- Keep PostgreSQL and Redis internal.
- Use volumes for database, resume storage, logs, and backups.
- Add health checks.

### 20.2 Nginx

Nginx should:

- expose web traffic on 80/443
- terminate HTTPS/TLS
- route frontend/backend traffic
- add security headers
- enforce request body size limits
- avoid serving protected resume storage directly

### 20.3 AWS VM

The provided AWS VM must serve the web frontend.

Expose publicly only:

- 80/443 for web traffic
- 22 for SSH, restricted where possible

Do not expose publicly:

- PostgreSQL
- Redis
- backend internal ports unless routed safely
- resume storage
- logs
- backups

---

## 21. Security Headers

Configure security headers where practical:

- `Content-Security-Policy`
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY` or CSP frame restrictions
- `Referrer-Policy`
- `Permissions-Policy`
- `Strict-Transport-Security` when HTTPS is stable

---

## 22. Testing Guidelines

### 22.1 General

Write tests for critical logic and security controls.

Minimum target:

- At least 70% unit test coverage for critical backend modules.

### 22.2 Authentication Tests

Test:

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

### 22.3 Authorization Tests

Test:

- user cannot view another user's profile
- user cannot update another user's profile
- user cannot access another user's resume
- user cannot access another user's saved jobs
- user cannot access another user's cover letters
- user cannot access admin routes
- admin can access admin routes

### 22.4 File Upload Tests

Test:

- valid PDF upload
- valid DOCX upload
- invalid extension rejected
- invalid MIME rejected
- forged MIME/content mismatch rejected
- oversized file rejected
- DOCX archive bomb or excessive archive structure rejected
- path traversal filename rejected
- parser failure handled safely

### 22.5 Job Tests

Test:

- job search works
- filters work
- pagination works
- duplicate job detection works
- suspicious job flagging works
- malicious HTML is sanitized or encoded
- external job links are validated or warned

### 22.6 AI Feature Tests

Test:

- recommendation generation works
- recommendation refresh respects ownership
- cover letter draft generation works
- cover letter editing works
- user cannot access another user's cover letter
- rate limiting applies where feasible

### 22.7 Audit Log Tests

Test:

- login events are logged
- upload events are logged
- admin actions are logged
- failed authorization attempts are logged
- sensitive values are not logged

### 22.8 Security Tests

Test:

- SQL injection attempts do not affect queries
- XSS payloads are not rendered unsafely
- unauthorized object access is blocked
- generic errors do not leak internals
- session invalidation works

---

## 23. CI/CD and Security Scanning

Add automated checks where possible:

- backend unit/integration tests
- frontend lint/build
- Bandit or Semgrep
- dependency vulnerability scanning
- Gitleaks secret scanning
- Trivy container scanning

CI should fail on:

- failing tests
- type/lint failures
- committed secrets
- critical dependency vulnerabilities unless documented and accepted
- obvious unsafe code patterns where practical

---

## 24. API Design Guidelines

### 24.1 General API Rules

- Use RESTful naming.
- Use consistent JSON responses.
- Use Pydantic response models.
- Use pagination for list endpoints.
- Validate sorting/filter fields using allowlists.
- Do not expose unnecessary internal implementation details.

### 24.2 Expected API Areas

Authentication:

- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/logout`
- `POST /auth/password-change`
- `POST /auth/password-reset/request`
- `POST /auth/password-reset/confirm`

Account/profile:

- `GET /me`
- `PATCH /me`
- `DELETE /me`
- `GET /me/profile`
- `PATCH /me/profile`

Resumes:

- `POST /resumes`
- `GET /resumes`
- `GET /resumes/{resume_id}`
- `DELETE /resumes/{resume_id}`
- `GET /resumes/{resume_id}/extraction`

Jobs:

- `GET /jobs`
- `GET /jobs/{job_id}`
- `POST /jobs/{job_id}/save`
- `DELETE /jobs/{job_id}/save`
- `GET /saved-jobs`

Recommendations:

- `POST /recommendations/refresh`
- `GET /recommendations`

Cover letters:

- `POST /jobs/{job_id}/cover-letter`
- `GET /cover-letters`
- `GET /cover-letters/{cover_letter_id}`
- `PATCH /cover-letters/{cover_letter_id}`

Application history:

- `GET /application-history`

Admin:

- `GET /admin/users`
- `PATCH /admin/users/{user_id}`
- `GET /admin/jobs`
- `PATCH /admin/jobs/{job_id}`
- `DELETE /admin/jobs/{job_id}`
- `GET /admin/scraping-runs`
- `GET /admin/audit-logs`
- `GET /admin/health`

---

## 25. Code Review Checklist

Before completing any feature, check:

- Are inputs validated?
- Are outputs encoded/sanitized?
- Are database queries safe?
- Are ownership/RBAC checks present?
- Is authentication required where appropriate?
- Is the action logged if security-relevant?
- Are sensitive values excluded from logs?
- Are errors safe for users?
- Are tests added?
- Are docs/tasks updated?
- Are secrets absent from code and commits?
- Does this change preserve least privilege?
- Does this change fail securely?
- Does this change follow `AGENTS.md`, `docs/PRD.md`, `docs/ARCHITECTURE.md`, and `docs/TASKS.md`?

---

## 26. Definition of Done

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
- Frontend handles errors safely.
- Documentation or task files are updated if architecture/behavior changes.
- No secrets are committed.
- The implementation follows this coding guideline file.

---

## 27. When Unsure

Choose the safer implementation.

Prefer:

- allowlists over blocklists
- backend enforcement over frontend-only checks
- secure defaults over optional security
- least privilege over broad access
- generic errors over detailed errors
- explicit validation over implicit trust
- auditability over silent changes
- fail-closed behavior over fail-open behavior
