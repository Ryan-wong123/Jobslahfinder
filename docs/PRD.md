# Product Requirements Document

## 1. Product Overview

This project is a secure AI-assisted job aggregation and application support platform for ICT2216 Secure Software Development.

The system helps job seekers:

- Browse consolidated job postings from approved sources.
- Search and filter job postings by keyword, company, location, category, and other supported fields.
- Upload resumes in approved file formats.
- Extract structured resume information such as skills, education, work history, and years of experience.
- Receive ranked job recommendations based on their extracted profile.
- Generate editable cover letter drafts for selected jobs.
- Save jobs for later viewing.
- Track generated cover letters and application preparation history.

The system helps administrators:

- Monitor scraping tasks.
- Manage users.
- Review scraping outcomes.
- Review, disable, and delete invalid, duplicate, malformed, or suspicious job postings.
- Monitor platform activity.
- Review audit logs for investigation and accountability.

The application handles sensitive personal data, uploaded files, external scraped content, generated AI content, and background processing. Security must therefore be built into the product from the requirements stage, not added only after implementation.

---

## 2. Problem Statement

Job seekers often browse multiple job portals manually, repeatedly enter the same search criteria, and spend additional time tailoring applications for each role. This system reduces that effort by centralizing job discovery and providing AI-assisted application preparation.

From a security perspective, the system is non-trivial because it:

- Stores account and profile data.
- Processes uploaded resumes containing personal data.
- Extracts and stores resume information.
- Stores generated cover letters and application preparation history.
- Consumes untrusted external job content.
- Connects to AI services.
- Runs scheduled scraping and background jobs.
- Provides administrator capabilities.

These characteristics create risks such as data leakage, account takeover, malicious file upload, job data poisoning, prompt injection, broken access control, denial of service, and log tampering. The product must therefore be designed with authentication, authorization, input validation, output encoding, audit logging, secure configuration, and least privilege from the start.

---

## 3. Stakeholders

### 3.1 Primary Users

#### Job Seekers
Individuals who use the system to browse job postings, upload resumes, receive recommendations, generate cover letter drafts, save jobs, and track application preparation activities.

#### Administrators
Trusted platform staff who monitor scraping jobs, manage accounts, moderate problematic postings, investigate incidents, review audit logs, and monitor system health.

### 3.2 Secondary Stakeholders

#### Developers and DevOps Maintainers
Responsible for coding, testing, deploying, patching, monitoring, and maintaining the system.

#### External Job Platforms
External websites such as JobStreet and MyCareersFuture that provide job posting data. These platforms influence scraping design, source attribution, data normalization, and external link handling.

#### AI Service Provider
External or internal AI provider used to support resume extraction, job recommendations, and cover letter drafting.

#### ICT2216 Teaching Team / Evaluators
Assess whether the application demonstrates secure software development principles, including requirements, misuse cases, risks, threat modelling, attack surface analysis, security architecture, security design, and secure implementation.

---

## 4. Goals

The system shall:

1. Provide a centralized job browsing and application preparation experience.
2. Reduce repetitive browsing across multiple job portals.
3. Support secure account registration, login, logout, password change, password reset, profile update, and account deletion.
4. Support secure resume upload, replacement, storage, and extraction.
5. Generate ranked job recommendations using profile and job data.
6. Generate editable cover letter drafts for user review.
7. Maintain saved jobs and application preparation history.
8. Provide administrative monitoring, moderation, and audit capabilities.
9. Demonstrate secure software development practices suitable for ICT2216.
10. Address risks identified during misuse case modelling, threat modelling, and attack surface analysis.

---

## 5. Non-Goals

The system shall not:

- Automatically submit applications to external job platforms.
- Replace official job portals.
- Scrape unapproved or unconfigured job sources.
- Expose resumes, extracted profiles, saved jobs, cover letters, recommendations, or application history to other normal users.
- Store plaintext passwords.
- Store plaintext password reset tokens or raw session tokens if server-side token storage is used.
- Store secrets, API keys, or private keys in source code.
- Trust external job content, uploaded files, frontend validation, or AI output as safe by default.
- Use administrator accounts as a backdoor to impersonate normal users.

---

## 6. User Roles and Permissions

### 6.1 Anonymous Visitor

Can:

- Register an account.
- Log in.
- Request password reset.
- View public landing pages if implemented.

Cannot:

- Upload resumes.
- Save jobs.
- Generate recommendations.
- Generate cover letters.
- View user-specific data.
- Access admin functions.

### 6.2 Authenticated Job Seeker

Can:

- View and update own account/profile.
- Delete own account after re-authentication or equivalent verification.
- Change own password.
- Upload, replace, and process own resume.
- Review and edit own extracted profile information.
- Search and view jobs.
- Save and unsave jobs.
- Generate recommendations based on own profile.
- Refresh recommendations after profile/resume updates.
- Generate and edit cover letter drafts.
- View own application preparation history.
- Log out securely.

Cannot:

- Access another user's account, profile, resume, saved jobs, recommendations, cover letters, or application history.
- Access admin functions.
- Modify job source configuration.
- View raw audit logs.
- Disable jobs.
- Bypass AI draft review and automatically submit applications externally.

### 6.3 Administrator

Can:

- Manage users.
- Review scraping outcomes.
- Disable or delete invalid, duplicate, malformed, or suspicious job postings.
- Monitor scraping task status.
- Monitor platform activity and system health.
- Review audit logs for investigation.

Cannot:

- Use admin access as a silent backdoor to impersonate users.
- Reset a user's password to a known value.
- Bypass audit logging.
- Access sensitive data without authorization, need, and traceability.

---

## 7. Functional Requirements

### 7.1 Job Aggregation and Job Browsing

- **FR1 Weekly job aggregation:** The system shall scrape job postings from selected job websites on a scheduled weekly basis and store normalized records in the internal database.
- **FR2 Job browsing and search:** The system shall allow users to browse, search, and filter job postings by keyword, company, location, category, and other supported fields.
- **FR9 Job detail viewing:** The system shall allow users to view detailed information for each job posting, including job title, company, description, source, posting date, and application link.
- **FR14 Redirect to original job source:** The system shall allow users to access the original job posting website through the provided application link.
- **FR16 Duplicate job handling:** The system shall detect and manage duplicate job postings collected from one or more job sources.
- **FR17 Scraping job monitoring:** The system shall allow administrators to view the execution status of scraping tasks, including successful runs, failed runs, and the number of job postings retrieved.
- **FR26 Salary comparison by experience:** The system shall allow users to compare advertised monthly salaries for a selected job role and optional validated location across Entry (0–2 years), Mid-level (3–5 years), Senior (6–9 years), and Lead/Expert (10+ years) minimum-experience bands. Each reportable band shall present the median, 25th–75th percentile range, qualifying-posting count, and change from the preceding reliable band. Bands containing fewer than five qualifying postings shall be identified as insufficient and shall not be plotted as reliable estimates.

Salary comparisons shall state the observation period and disclose that advertised salary is not guaranteed compensation. Only active, non-suspicious postings with explicit minimum experience, complete valid salary bounds, SGD currency, and a supported salary period shall qualify.

### 7.2 Resume and Profile

- **FR3 Resume upload:** The system shall allow authenticated users to upload a resume in approved file formats for profile enhancement and recommendation.
- **FR4 Resume information extraction:** The system shall extract structured information from uploaded resumes, including skills, education, work history, and years of experience.
- **FR10 Resume update and replacement:** The system shall allow users to replace or update their previously uploaded resume when newer information is available.
- **FR11 User profile editing:** The system shall allow users to review and edit extracted resume information if the system-generated profile contains incomplete or inaccurate details.

### 7.3 Recommendation and Cover Letter

- **FR5 Job recommendation:** The system shall match the extracted user profile against stored jobs and present ranked recommendations.
- **FR6 Cover letter draft generation:** The system shall generate a draft cover letter tailored to a selected job posting using the user's profile and the job description.
- **FR12 Recommendation refresh:** The system shall allow users to regenerate job recommendations after updating their resume or profile information.
- **FR15 Cover letter editing:** The system shall allow users to review and edit generated cover letter drafts before using them for job applications.

### 7.4 Saved Jobs and Application History

- **FR7 Application preparation history:** The system shall allow users to view previously generated cover letters and a history of jobs for which they prepared an application.
- **FR13 Bookmark or save jobs:** The system shall allow users to save selected job postings for future viewing.

### 7.5 Administration

- **FR8 Administrative management:** The system shall allow administrators to manage users, review scraping outcomes, disable or delete invalid jobs, and monitor platform activity.

### 7.6 Account Management

- **FR18 Account registration (Create):** The system shall allow new users to create an account by submitting the required registration details.
- **FR19 Account profile viewing (Read):** The system shall allow authenticated users to view their account and profile information.
- **FR20 Account profile update (Update):** The system shall allow authenticated users to update their account and profile information.
- **FR21 Account deletion (Delete):** The system shall allow authenticated users to delete their account.
- **FR22 User login:** The system shall allow registered users to log in using their account credentials.
- **FR23 User logout:** The system shall allow authenticated users to log out of the system securely.
- **FR24 Password change:** The system shall allow authenticated users to change their account password.
- **FR25 Password reset:** The system shall allow users to reset their password through a verified account recovery process.

---

## 8. Non-Functional Requirements

### 8.1 Availability and Performance

- **NFR1 Availability:** The system shall maintain at least 99% availability per month for normal job browsing and profile access, excluding scheduled maintenance periods.
- **NFR2 Performance:** The system shall allow search results, job detail pages, and profile views to return within 3 seconds for at least 95% of user requests under normal load.
- **NFR3 Scalability:** The system shall support at least 1,000 registered users and 50,000 stored job postings without requiring major architectural redesign.
- **NFR8 Reliability:** The system shall complete job aggregation, resume processing, recommendation generation, and cover letter generation successfully for at least 95% of valid requests under normal operating conditions.
- **NFR13 Resource efficiency:** The system shall operate within the resource limits of the provided AWS VM under normal load and shall not exceed 80% average CPU usage or 80% average memory usage for prolonged periods.

### 8.2 Maintainability, Extensibility, and Portability

- **NFR4 Maintainability:** The system shall use modular components so that scraping, parsing, recommendation, and cover letter generation can be modified independently with minimal impact on other modules.
- **NFR9 Extensibility:** The system shall allow the addition of at least one new job source or AI service with changes limited mainly to the relevant integration module, without requiring major redesign of the overall system.
- **NFR11 Portability:** The system shall be deployable in a consistent manner across development, testing, and production environments using the same containerized setup and configuration structure.

### 8.3 Usability

- **NFR5 Usability:** The system shall enable at least 80% of test users to complete the main tasks of uploading a resume, browsing jobs, and generating a cover letter without external assistance during usability testing.
- **NFR17 Account management accessibility:** The system shall provide login and account management functions through a clear and consistent interface that allows users to access account registration, profile viewing, profile update, password change, and account deletion functions without unnecessary navigation steps.
- **NFR23 Account operation clarity:** The system shall provide clear success and failure messages for account registration, login, profile update, password change, and account deletion operations without exposing sensitive internal details.

### 8.4 Auditability and Monitoring

- **NFR6 Auditability:** The system shall log important security and administrative events with sufficient detail, including timestamp, user ID where applicable, event type, and outcome, and shall retain such logs for at least 90 days.
- **NFR12 Monitoring support:** The system shall provide operational information such as service uptime, scraping task status, background job status, and error logs, and administrators shall be able to review this information within 1 minute of access.
- **NFR21 Account operation traceability:** The system shall ensure that account registration, login, profile update, password change, and account deletion actions are traceable to the relevant user or session for investigation purposes.

### 8.5 Data Integrity, Privacy, and Recovery

- **NFR7 Recoverability:** The system shall back up critical application data at least once every 24 hours and shall be restorable within 4 hours after a major failure.
- **NFR10 Data consistency:** The system shall ensure that updates to jobs, profiles, and recommendations are reflected consistently across the frontend, backend, and database with no unresolved conflicting records in normal operation.
- **NFR18 Account data integrity:** The system shall ensure that account creation, profile update, password change, and account deletion operations do not result in partial, duplicate, or corrupted account records.
- **NFR19 Account privacy:** The system shall ensure that user account details are only visible to the owning user and authorized administrators during account profile viewing and management operations.
- **NFR20 Account session continuity:** The system shall maintain a stable authenticated session during normal account profile viewing and update operations unless the session expires, the user logs out, or a security event requires session invalidation.
- **NFR22 Account recovery support:** The system shall provide a verified account recovery mechanism that allows legitimate users to regain access to their accounts without manual administrator intervention.

### 8.6 Testability, Data Quality, and Error Handling

- **NFR14 Testability:** The system shall support automated unit, integration, and security testing, with at least 70% unit test coverage for critical backend modules.
- **NFR15 Data quality:** The system shall validate and normalize scraped job data so that at least 95% of stored job postings contain the required core fields such as job title, company, source, and application link.
- **NFR16 Error handling quality:** The system shall handle failures gracefully and provide useful feedback to users while ensuring that no sensitive internal details, such as stack traces or configuration values, are exposed through the user interface.
- **NFR24 Account management security support:** The system shall protect login and account management functions using appropriate authentication, authorization, session management, and secure communication controls.

---

## 9. Security Requirements

### 9.1 Secure Functional Requirements

- **SFR1 Secure account profile viewing:** The system shall allow authenticated users to view only their own account and profile information unless the requester is an authorized administrator.
- **SFR2 Secure account profile update:** The system shall allow authenticated users to update only their own account and profile information.
- **SFR3 Secure account deletion:** The system shall allow authenticated users to delete only their own account after successful re-authentication or equivalent verification.
- **SFR4 Secure saved jobs access:** The system shall ensure that bookmarked or saved jobs are accessible only to the owning user and authorized administrators.
- **SFR5 Secure application preparation history access:** The system shall ensure that previously generated cover letters and application preparation history are accessible only to the owning user and authorized administrators.
- **SFR6 Controlled cover letter generation:** The system shall present AI-generated cover letters as drafts for user review and shall not automatically submit them to external job platforms without explicit user confirmation.
- **SFR7 Trusted job scraping sources:** The system shall retrieve job postings only from approved and configured job sources.
- **SFR8 Duplicate and suspicious job control:** The system shall detect, flag, and manage duplicate, malformed, or suspicious job postings before they are presented to users.

### 9.2 Functional Security Requirements

- **FSR1 Secure authentication:** The system shall require authenticated access for all user-specific functions, including resume upload, job recommendations, saved jobs, cover letter generation, application history viewing, and account profile management.
- **FSR2 Secure password storage:** The system shall store user passwords using strong password hashing and shall never store passwords in plaintext.
- **FSR3 Secure session management:** The system shall use secure session tokens that are random, hard to guess, expire after a defined period of inactivity, and are invalidated upon logout.
- **FSR4 Role-based access control:** The system shall enforce role-based access control so that normal users can only access their own data, while administrative functions are restricted to authorized administrators.
- **FSR5 Secure file upload validation:** The system shall validate uploaded resume files by checking file extension, declared MIME type, content-derived file type, file size, file signatures or document structure, archive safety for DOCX files, and path traversal attempts, and shall reject unsupported or potentially malicious files.
- **FSR6 Secure storage of uploaded files:** The system shall store uploaded resume files in a protected location outside publicly accessible web directories.
- **FSR7 Logging and audit trail:** The system shall log security-relevant events, including registration attempts, login attempts, failed access attempts, resume uploads, password changes, password reset requests, admin actions, and scraping failures, for auditing and investigation purposes.
- **FSR8 Protection of logs:** The system shall protect system logs from unauthorized access or tampering and shall avoid storing sensitive information such as passwords, reset tokens, session tokens, raw resume contents, AI prompts, generated cover letters, or edited cover letters in logs.
- **FSR9 Rate limiting:** The system shall apply rate limiting to sensitive functions such as registration, login, password reset, resume upload, and cover letter generation to reduce the risk of brute-force attacks and service abuse.
- **FSR10 Password recovery security:** The system shall provide a verified password reset mechanism that uses secure, time-limited, single-use recovery tokens with strict format validation or equivalent controls to prevent unauthorized account recovery.
- **FSR11 Secure backup protection:** The system shall protect backup copies of account data, resumes, extracted profile information, and application records against unauthorized access and tampering.

### 9.3 Non-Functional Security Requirements

- **NFSR1 Secure transmission of data:** The system shall protect all data transmitted between users and the website using HTTPS/TLS.
- **NFSR2 Account privacy protection:** The system shall protect account and profile information so that such information is accessible only to the owning user and authorized administrators.
- **NFSR3 Resume confidentiality:** The system shall protect uploaded resumes and extracted resume information so that they are accessible only to the owning user and authorized administrators.
- **NFSR4 Input validation:** The system shall validate all user input, AI-related input and output, uploaded files, route/query parameters, and external scraped data before processing or storing it in order to reduce the risk of injection, malformed data attacks, malicious uploads, and log bloat.
- **NFSR5 Output encoding:** The system shall encode or sanitize displayed content, including scraped job descriptions, profile content, extracted resume fields, AI-generated output, admin-visible text, and user-generated content, to reduce the risk of cross-site scripting attacks.
- **NFSR6 Database query protection:** The system shall use parameterized queries or ORM-based protections for all database operations involving user input or external data.
- **NFSR7 Availability of core services:** The system shall separate background tasks such as scraping, resume extraction, recommendation generation, and cover letter generation from the main web service so that long-running jobs do not affect normal user access.
- **NFSR8 Protection against unauthorized data access:** The system shall ensure that users cannot access, modify, or delete resumes, cover letters, recommendations, saved jobs, or application records belonging to other users.
- **NFSR9 Secure admin access:** The system shall require stronger protection for administrative accounts, such as stricter access control, stronger authentication requirements, and optional multi-factor authentication.
- **NFSR10 Account operation integrity:** The system shall ensure that account registration, profile update, password change, and account deletion operations do not result in partial, duplicate, or corrupted account records.
- **NFSR11 Error handling security:** The system shall return generic error messages to users and shall not expose internal system details, stack traces, or sensitive configuration information through the interface.

### 9.4 Secure Development Requirements

- **SDR1 Dependency and code security checks:** The system shall include automated security checks in the development pipeline, such as static code analysis, dependency vulnerability scanning, and secret detection before deployment.
- **SDR2 Secure code management:** The development process shall prevent hardcoded credentials, secrets, and private keys from being committed into source control repositories.
- **SDR3 Secure configuration management:** The development and deployment process shall store sensitive configuration values securely and shall not expose them in source code or user-facing outputs.
- **SDR4 Security testing methodology:** The development process shall include automated unit, integration, and security testing for critical backend modules before deployment.

---

## 10. Abuse and Misuse Case Summary

The product must defend against the following grouped misuse cases:

| Misuse Case | Description | Related Requirements |
|---|---|---|
| MU1 Account compromise / unauthorized account operation | Brute force, credential stuffing, account enumeration, session hijacking, unauthorized profile update/delete, password reset abuse | FR18-FR25, NFR18-NFR24, FSR1-FSR4, FSR9-FSR10 |
| MU2 Malicious resume upload / resume data exposure | Malicious file upload, oversized file, fake file type, parsing abuse, unauthorized resume/profile access | FR3, FR4, FR10, FR11, FSR5-FSR6, NFSR3-NFSR4 |
| MU3 Poisoned job data / injection / malicious redirect | Untrusted scraping source, duplicate/malformed jobs, SQL injection, XSS in job descriptions, phishing links | FR1, FR2, FR9, FR14, FR16, SFR7-SFR8, NFSR4-NFSR6 |
| MU4 AI abuse / prompt injection / generated content misuse | Prompt injection, manipulated recommendations, unsafe generated cover letters, excessive generation requests | FR5, FR6, FR12, FR15, SFR6, FSR9 |
| MU5 Unauthorized access to saved jobs or application history | Accessing another user's saved jobs, cover letters, or application history | FR7, FR13, SFR4-SFR5, NFSR8 |
| MU6 Admin abuse / privilege escalation / log tampering | Unauthorized admin access, rogue admin misuse, scraping status manipulation, audit log tampering | FR8, FR17, NFR6, NFR12, FSR7-FSR8, NFSR9 |
| MU7 Service abuse / DoS / background job exhaustion | Bot scraping, mass search, repeated uploads, AI generation abuse, scraping overload | NFR1-NFR3, NFR7-NFR8, NFR13, NFSR7 |
| MU8 Insecure development / secret leakage / vulnerable dependency | Hardcoded secrets, insecure configuration, vulnerable libraries, missing tests | SDR1-SDR4, NFR4, NFR11, NFR14 |

---

## 11. Critical Risks

| Risk ID | Risk | Impact | Likelihood | Criticality | Mitigation Summary |
|---|---|---:|---:|---:|---|
| R1 | Data leakage of resumes, profiles, and cover letters | High | Medium | Critical | RBAC, ownership checks, HTTPS/TLS, protected file storage, audit logging, no sensitive data in logs |
| R2 | Account takeover | High | Medium | Critical | Password hashing, rate limiting, secure reset tokens, session expiry, generic errors |
| R3 | Broken access control / privilege escalation | High | Medium | Critical | Backend authorization checks, RBAC, admin hardening |
| R4 | Malicious resume upload | High | Medium | High | File allowlist, MIME/content checks, size limit, store outside web root, worker isolation |
| R5 | Job data poisoning / malicious scraped content | High | Medium | High | Source allowlist, normalization, duplicate detection, output encoding, suspicious link flagging |
| R6 | Prompt injection / AI misuse | Medium-High | Medium | High | Prompt separation, input length limits, data minimization, output review, draft-only generation |
| R7 | Denial of service / resource exhaustion | High | Medium | High | Rate limiting, background workers, Redis queue, request size limits, monitoring |
| R8 | Log tampering or sensitive data in logs | Medium-High | Medium | High | Restricted log access, redaction, retention, log integrity controls |
| R9 | Insecure secrets / vulnerable dependencies | High | Medium | High | Gitleaks, dependency scanning, Semgrep/Bandit, environment variables, secure config |
| R10 | Backup exposure or recovery failure | High | Low-Medium | Medium-High | Encrypted backups, access control, restore testing, retention policy |
| R11 | Incorrect or misleading AI output | Medium | Medium | Medium | User review, editable drafts, disclaimer, recommendation rationale |
| R12 | Scraping failure or stale job data | Medium | Medium | Medium | Scraping monitoring, retry policy, admin review, source attribution, stale job expiry |

---

## 12. Product Architecture Requirements

The expected architecture is:

- Frontend: Next.js + React + TypeScript + Tailwind CSS.
- Backend API: FastAPI + Python.
- Database: PostgreSQL.
- Queue/cache: Redis.
- Background jobs: Celery or RQ.
- Reverse proxy/deployment: Nginx + Docker Compose on the provided AWS VM.
- Security tooling: Semgrep/Bandit, Gitleaks, Trivy, dependency scanners.

The frontend and backend should remain separate logical components even if hosted on the same AWS VM. Long-running tasks such as scraping, resume parsing, recommendation generation, and cover letter generation must be separated from normal web request handling using a worker and queue design.

---

## 13. Main API Requirements

### 13.1 Auth APIs

- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/logout`
- `POST /auth/password-change`
- `POST /auth/password-reset/request`
- `POST /auth/password-reset/confirm`

### 13.2 Account/Profile APIs

- `GET /me`
- `PATCH /me`
- `DELETE /me`
- `GET /me/profile`
- `PATCH /me/profile`

### 13.3 Resume APIs

- `POST /resumes`
- `GET /resumes`
- `GET /resumes/{resume_id}`
- `DELETE /resumes/{resume_id}`
- `GET /resumes/{resume_id}/extraction`

### 13.4 Job APIs

- `GET /jobs`
- `GET /jobs/{job_id}`
- `POST /jobs/{job_id}/save`
- `DELETE /jobs/{job_id}/save`
- `GET /saved-jobs`

### 13.5 Recommendation APIs

- `POST /recommendations/refresh`
- `GET /recommendations`

### 13.6 Cover Letter APIs

- `POST /jobs/{job_id}/cover-letter`
- `GET /cover-letters`
- `GET /cover-letters/{cover_letter_id}`
- `PATCH /cover-letters/{cover_letter_id}`

### 13.7 Application History APIs

- `GET /application-history`

### 13.8 Admin APIs

- `GET /admin/users`
- `PATCH /admin/users/{user_id}`
- `GET /admin/jobs`
- `PATCH /admin/jobs/{job_id}`
- `DELETE /admin/jobs/{job_id}`
- `GET /admin/scraping-runs`
- `GET /admin/audit-logs`
- `GET /admin/health`

---

## 14. Data Requirements

The system must store and manage the following entities:

- Users
- Sessions
- Password reset tokens
- User profiles
- Resumes
- Resume extractions
- Job sources
- Scraping runs
- Job postings
- Saved jobs
- Recommendations
- Cover letters
- Application history
- Audit logs

Sensitive data includes:

- Password hashes
- Session token hashes
- Password reset token hashes
- Email addresses
- Profile information
- Phone numbers
- Uploaded resumes
- Extracted resume text
- Skills, education, and work history
- Generated cover letters
- Application history
- Audit logs
- Backup data
- API keys and secrets

The system must not store plaintext passwords, raw reset tokens, raw session tokens, or secrets in source code.

---

## 15. Acceptance Criteria

The MVP is acceptable when:

- Users can register, log in, log out, change password, reset password, and manage their profile.
- Users can delete their own account after re-authentication or equivalent verification.
- Users can upload resumes securely and see extracted profile information.
- Users can edit extracted profile information.
- Jobs can be scraped or seeded from approved sources, normalized, searched, filtered, and viewed.
- Duplicate and suspicious jobs can be detected or flagged.
- Users can save and unsave jobs.
- Users can generate ranked job recommendations.
- Users can generate and edit cover letter drafts.
- The application does not automatically submit generated cover letters to external platforms.
- Users can view their own application preparation history.
- Admins can view scraping runs, manage users, moderate jobs, and review audit logs.
- RBAC and ownership checks prevent unauthorized data access.
- Security-relevant events are logged without exposing sensitive information.
- File upload validation rejects unsupported, oversized, or suspicious files.
- Scraped content is encoded or sanitized before display.
- Password reset tokens are time-limited, single-use, and stored hashed.
- Sessions expire and are invalidated on logout.
- Critical tests and security scans pass.
- Docker Compose deployment works on the provided AWS VM.

---

## 16. Testing Acceptance Criteria

The system should include tests for:

### Authentication

- Successful registration.
- Duplicate registration rejected.
- Successful login.
- Failed login with generic error.
- Logout invalidates session.
- Password change.
- Password reset request.
- Password reset confirmation.
- Expired reset token rejected.
- Reused reset token rejected.

### Authorization

- User cannot view another user's profile.
- User cannot update another user's profile.
- User cannot access another user's resume.
- User cannot access another user's saved jobs.
- User cannot access another user's recommendations.
- User cannot access another user's cover letters.
- User cannot access another user's application history.
- Normal user cannot access admin routes.
- Admin can access admin routes.

### Resume Upload

- Valid PDF upload accepted.
- Valid DOCX upload accepted.
- Invalid extension rejected.
- Invalid MIME type rejected.
- Oversized file rejected.
- Path traversal filename rejected.
- Parser failure handled safely.

### Jobs and Scraping

- Job search works.
- Filters work.
- Pagination works.
- Duplicate job detection works.
- Suspicious job flagging works.
- Malicious HTML is not rendered unsafely.
- External job links are validated or warned.

### AI Features

- Recommendation generation works.
- Cover letter draft generation works.
- Cover letter editing works.
- Generated cover letter belongs to correct user.
- Rate limiting applies to generation endpoints.
- AI output remains draft-only.

### Audit Logging

- Login events are logged.
- Password reset events are logged.
- Resume upload events are logged.
- Admin actions are logged.
- Failed authorization attempts are logged.
- Sensitive values are not logged.

Minimum target:

- At least 70% unit test coverage for critical backend modules.

---

## 17. Deployment Acceptance Criteria

Deployment is acceptable when:

- The web frontend is served from the provided AWS VM.
- Nginx routes traffic to frontend and backend.
- HTTPS/TLS is configured for production.
- PostgreSQL is not publicly exposed.
- Redis is not publicly exposed.
- Resume storage is not publicly exposed.
- Logs and backups are not publicly exposed.
- Debug mode is disabled in production.
- Environment variables are configured securely.
- `.env` is not committed.
- Health checks are available.
- Background workers are running.
- Scraping schedule works.
- Backup process is documented or scripted.
- Smoke tests pass after deployment.

---

## 18. Traceability Matrix

| Feature / Risk Area | Functional Requirements | Security Requirements | Primary Risks |
|---|---|---|---|
| Account and authentication | FR18-FR25 | SFR1-SFR3, FSR1-FSR4, FSR9-FSR10, NFSR1, NFSR10-NFSR11 | R2, R3 |
| Resume upload and extraction | FR3, FR4, FR10, FR11 | FSR5-FSR6, NFSR3-NFSR4, NFSR8 | R1, R4 |
| Job aggregation and browsing | FR1, FR2, FR9, FR14, FR16, FR17 | SFR7-SFR8, NFSR4-NFSR6 | R5, R12 |
| Recommendations and cover letters | FR5, FR6, FR12, FR15 | SFR6, FSR9, NFSR7 | R6, R7, R11 |
| Saved jobs and history | FR7, FR13 | SFR4-SFR5, NFSR8 | R1, R3 |
| Admin and monitoring | FR8, FR17 | FSR4, FSR7-FSR8, NFSR9 | R3, R8 |
| Availability and recovery | NFR1, NFR7, NFR8, NFR13 | FSR11, NFSR7 | R7, R10 |
| Secure development | NFR14 | SDR1-SDR4 | R9 |

---

## 19. Definition of Done

A feature is done only when:

- The backend endpoint is implemented.
- Input validation exists.
- Authentication is required where appropriate.
- RBAC or ownership checks are applied where appropriate.
- Database operations are safe.
- Security-relevant actions are audit logged.
- Sensitive values are not logged.
- User-facing errors are safe and generic.
- Frontend flow is implemented where applicable.
- Tests cover success and failure cases.
- Documentation is updated where architecture or behaviour changes.
- No secrets are committed.
