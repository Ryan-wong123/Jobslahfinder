# Security Hardening Implementation Prompts

Use these prompts one at a time. Before implementing any prompt, read `AGENTS.md`, `docs/PRD.md`, `docs/ARCHITECTURE.md`, `docs/CODING_GUIDELINES.md`, and `docs/TASKS.md`, then keep the change scoped to the named hardening task. Do not remove existing authentication, authorization, validation, audit logging, or tests to make a change pass. After the task is implemented and verified, update the matching checkbox in `docs/TASKS.md` from `[ ]` to `[x]`; leave it unchecked if tests were not run or work remains.

---

## 1. Shared Text Validation And Sanitization Helper

Implement a shared backend text validation/sanitization helper for user profile text, resume extraction edits, AI output, scraped job text, and admin-visible text.

Review the existing validators and cleaners in `backend/app/schemas/auth.py`, `backend/app/schemas/resumes.py`, `backend/app/services/jobs.py`, and `backend/app/services/activity.py`. Create or reuse an appropriate shared module, then migrate duplicated logic where safe. The helper should support trimming, maximum length enforcement, optional empty-to-null behavior, optional HTML rejection or stripping, and clear validation errors. Preserve existing API behavior unless the current behavior is unsafe. Add or update tests for profile text, resume extraction edits, scraped job text, cover letter text, and AI-generated output.

Acceptance criteria:
- Shared helper is used by the major text input/output paths.
- Existing security tests still pass.
- XSS payloads are stored or returned only as safe text.
- No raw SQL or unsafe HTML rendering is introduced.

---

## 2. Unicode And Control Character Normalization

Normalize Unicode and reject or strip unsafe control characters consistently before storing or returning text fields.

Add Unicode normalization, for example NFKC where appropriate, and consistent control-character handling to the shared text validation path. Preserve normal whitespace needed for user text, but reject or remove null bytes, hidden control characters, and other unsafe non-printing characters that can confuse logs, displays, or comparisons. Apply the behavior to profile fields, resume extraction edits, scraped job fields, cover letter edits, AI output normalization, and audit-visible text where appropriate.

Acceptance criteria:
- Unsafe control characters are rejected or safely stripped consistently.
- Valid names, summaries, skills, job descriptions, and cover letters still work.
- Tests cover null bytes, bidi/control characters where practical, and normal multiline text.

---

## 3. Password Reset Token Format Validation

Add strict password reset token validation using an allowlist pattern for the expected generated token format.

Inspect token generation in `backend/app/security/tokens.py` and reset confirmation in `backend/app/schemas/auth.py` and `backend/app/services/auth.py`. Update `PasswordResetConfirmRequest.token` so it accepts only the actual generated token character set and length range. Keep reset errors generic and do not reveal whether a token exists. Add tests for valid tokens, invalid characters, whitespace, overlong tokens, short tokens, expired tokens, and reused tokens.

Acceptance criteria:
- Invalid token formats fail request validation before service logic.
- Reset token values are never logged.
- Existing password reset tests continue to pass or are updated for the stricter format.

---

## 4. Lock Down Public Suspicious And Inactive Job Filters

Remove public access to inactive or suspicious job postings by locking down or removing public `active_only` and `include_suspicious` job search parameters.

Update `GET /jobs` in `backend/app/api/jobs.py` so public users can only browse active, non-suspicious jobs. Remove public query parameters that allow callers to request inactive or suspicious postings, or ignore them fail-closed. Ensure `backend/app/services/jobs.py` still supports admin use if needed, but public route calls must not expose moderated content. Update frontend job browsing if it references those parameters. Add tests showing public `/jobs` never returns inactive or suspicious jobs even if query strings are provided.

Acceptance criteria:
- Public `/jobs` returns only active and non-suspicious jobs.
- Suspicious/inactive jobs remain accessible only through admin moderation routes.
- Existing job search, filters, and pagination still work.

---

## 5. Keep Moderation Filters Admin-Only

Keep inactive and suspicious job listing controls admin-only through `/admin/jobs`.

Review `backend/app/api/admin.py` and frontend admin job moderation components. Ensure `is_active`, `is_suspicious`, and any moderation-only filters are accepted only on admin endpoints protected by `require_admin`. Confirm normal users cannot reach these controls through public APIs or frontend route hiding. Add or update tests proving normal users and anonymous users cannot use admin filters, while admins can.

Acceptance criteria:
- Admin `/admin/jobs` supports moderation filters.
- Public routes do not expose moderation filters.
- Authorization failures are safely handled and audit logged where applicable.

---

## 6. Interview Question Response Schemas

Add strict response schemas for AI-derived interview question generation output.

Find `/jobs/{job_id}/interview-questions` in `backend/app/api/jobs.py` and the generation helpers in `backend/app/services/activity.py`. Create Pydantic response models for the interview question payload, including `job_id`, `resume_id`, `generated_by`, and a bounded list of question items. Each item should validate category, difficulty, and question length using allowlists and length limits. Use the response model on the route and validate service output before returning it. Add tests for malformed AI output, overlong questions, invalid categories, invalid difficulties, duplicate questions, and normal generation.

Acceptance criteria:
- The route has an explicit `response_model`.
- AI output is validated and normalized before response.
- Malformed AI output cannot produce arbitrary JSON to the frontend.

---

## 7. Roadmap Skill Length Rejection

Replace silent roadmap skill truncation with explicit validation and rejection for overlong skill values.

Inspect `backend/app/schemas/roadmaps.py`, especially `RoadmapCreateRequest.validate_current_skills`. Replace silent `cleaned[:80]` truncation with explicit length validation. Keep duplicate removal and maximum list size behavior clear. Add tests for valid skills, duplicate skills, blank skills, too many skills, and a skill longer than the allowed length.

Acceptance criteria:
- Overlong skill values are rejected with a generic validation response.
- Valid roadmap creation still works.
- No silent mutation hides invalid or malicious input.

---

## 8. External Job URL Hardening

Reject external job URLs with credentials, invalid hosts, non-HTTPS schemes, excessive length, or domains outside the approved source allowlist.

Review URL validation in `backend/app/services/jobs.py`, especially `validate_https_url`, `validate_source_base_url`, and `validate_job_url_for_source`. Strengthen validation to reject URLs with username/password components, missing hosts, non-HTTPS schemes, disallowed domains, unsafe lengths, and malformed values. Keep exact approved source domain behavior unless a documented subdomain policy is required. Add tests for phishing-style URLs, credentialed URLs, `javascript:` URLs, HTTP URLs, very long URLs, allowed source URLs, and source/domain mismatch.

Acceptance criteria:
- Only approved HTTPS job URLs are stored or returned.
- Credentialed and malformed URLs are rejected.
- Existing scraper normalization tests still pass with approved URLs.

---

## 9. Content-Derived Resume MIME Validation

Add content-derived MIME validation for resume uploads instead of trusting only the client-provided `UploadFile.content_type`.

Review `backend/app/services/resumes.py`, especially `validate_mime_type`, `validate_file_signature`, and `validate_upload_file`. Derive file type from content signatures or safe parser checks, compare it with extension and declared MIME, and reject mismatches. Do not trust the filename or client MIME alone. Keep accepted formats limited to PDF and DOCX. Add tests where a PDF is uploaded with DOCX MIME, a DOCX is uploaded with PDF MIME, a valid file has the correct MIME, and a forged file has a valid extension but invalid content.

Acceptance criteria:
- Extension, declared MIME, and content-derived type must agree.
- Valid PDF and DOCX uploads still pass.
- MIME mismatch and forged content are rejected with safe errors.

---

## 10. DOCX Archive Bomb Protection

Add DOCX zip-bomb protections: maximum archive entry count, maximum total uncompressed bytes, and maximum compression ratio.

Update DOCX validation and parsing in `backend/app/services/resumes.py`. When opening DOCX files, inspect archive members before extracting or reading document XML. Enforce limits for member count, total uncompressed size, individual file size, and compression ratio. Reject suspicious archives with the existing generic upload/parser error pattern and metadata-only audit details. Add tests for a valid DOCX, excessive entry count, excessive uncompressed size, high compression ratio, and missing required DOCX files.

Acceptance criteria:
- Valid DOCX uploads and parsing still work.
- Archive bomb patterns are rejected safely.
- No full document content is logged.

---

## 11. Positive Admin Path Parameter Validation

Use positive path parameter validation consistently for admin route IDs such as job source IDs.

Search admin and non-admin API modules for path parameters declared as plain `int`. Replace resource IDs with existing positive ID aliases such as `PositiveId` or define equivalent `Annotated[int, Path(gt=0)]`. Pay special attention to `/admin/job-sources/{source_id}` in `backend/app/api/admin.py`. Add tests showing zero, negative, and non-integer IDs are rejected with generic validation responses.

Acceptance criteria:
- All resource path IDs enforce positive integer validation.
- Admin route behavior is unchanged for valid IDs.
- Request validation errors remain generic.

---

## 12. Remove Raw Resume Text Debug Printing

Remove raw extracted resume text debug printing from the Gemini resume extraction path.

Inspect `parse_resume_with_gemini_timeout` in `backend/app/services/resumes.py`. Remove any `print()` or logging that outputs extracted resume text, raw resume contents, or prompt content. If debugging metadata is needed, log only safe metadata such as character count, provider name, resume ID where available, and outcome. Add a test or log-capture assertion proving raw resume text is not printed or logged during extraction.

Acceptance criteria:
- No raw resume text is printed to stdout/stderr or application logs.
- Gemini extraction still receives bounded text internally.
- Audit logs remain metadata-only.

---

## 13. Bound Audit Detail And User-Agent Strings

Add maximum length limits and safe truncation for nested audit log detail strings and user-agent values.

Review `backend/app/services/audit.py`. Extend audit detail sanitization so nested strings are bounded, sensitive keys are still redacted, nested lists/dicts are handled safely, and extremely large attacker-controlled values cannot bloat logs. Keep `user_agent` bounded. Add tests for nested sensitive keys, nested long strings, long lists, non-string scalar values, and user-agent truncation.

Acceptance criteria:
- Audit details are recursively redacted and bounded.
- Sensitive values remain redacted.
- Large attacker-controlled details do not create oversized audit records.

---

## 14. Sensitive Logging Regression Tests

Add tests proving full resume text, AI prompts, generated cover letters, and edited cover letters are not written to application logs or audit details.

Review existing security tests in `backend/app/tests/test_security_phase12.py` and related feature tests. Add regression tests that exercise resume extraction failure/success, cover letter generation/editing, AI prompt construction paths where practical, and audit log creation. Use unique sentinel strings for secrets or sensitive content and assert those strings do not appear in audit details, captured logs, stdout, or stderr. Keep tests deterministic and avoid real external AI calls.

Acceptance criteria:
- Tests fail if raw resume text, prompts, generated cover letters, or edited cover letters are logged.
- Tests run offline without real Gemini/API calls.
- Existing audit logging functionality remains intact.
