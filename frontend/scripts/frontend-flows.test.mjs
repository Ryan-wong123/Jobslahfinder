import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { join } from "node:path";
import { test } from "node:test";

const root = fileURLToPath(new URL("..", import.meta.url));

function readProjectFile(...segments) {
  return readFileSync(join(root, ...segments), "utf8");
}

function readComponent(name) {
  return readProjectFile("src", "components", `${name}.tsx`);
}

function readPage(...segments) {
  return readProjectFile("src", "app", ...segments, "page.tsx");
}

test("all implemented frontend routes mount their expected feature components", () => {
  const routeComponents = [
    [["page"], "HomeHub"],
    [["account"], "AccountPanel"],
    [["admin"], "AdminScrapingPanel"],
    [["admin", "scraping-runs", "[runId]"], "AdminScrapingRunDetailPanel"],
    [["admin", "users", "[userId]"], "AdminUserDetailPanel"],
    [["application-history"], "ApplicationHistoryPanel"],
    [["cover-letters"], "CoverLettersPanel"],
    [["cover-letters", "[coverLetterId]"], "CoverLetterEditor"],
    [["jobs"], "JobBrowser"],
    [["jobs", "[jobId]"], "JobDetailPanel"],
    [["recommendations"], "RecommendationsPanel"],
    [["resumes"], "ResumeWorkspace"],
    [["resumes", "[resumeId]"], "ResumeDetailPanel"],
    [["resumes", "[resumeId]", "profile"], "ExtractedProfilePanel"],
    [["resumes", "[resumeId]", "profile", "edit"], "ExtractedProfilePanel"],
    [["roadmaps"], "RoleCatalogPanel"],
    [["roadmaps", "[slug]"], "RoleDetailPanel"],
    [["saved-jobs"], "SavedJobsPanel"],
    [["two-factor", "setup"], "TwoFactorSetupPanel"],
    [["two-factor", "verify"], "TwoFactorVerifyPanel"],
    [["salary-trends"], "SalaryTrendPanel"]
  ];

  for (const [route, component] of routeComponents) {
    const page = route.length === 1 && route[0] === "page" ? readPage() : readPage(...route);
    assert.match(page, new RegExp(`import \\{ ${component} \\}`));
    assert.match(page, new RegExp(`<${component}(\\s|[>/])`));
  }
});

test("two-factor pages cover setup, confirmation, challenge verification, and safe redirects", () => {
  const setupPanel = readComponent("TwoFactorSetupPanel");
  const verifyPanel = readComponent("TwoFactorVerifyPanel");

  assert.match(setupPanel, /apiFetch<TwoFactorSetup>\("\/auth\/2fa\/setup"\)/);
  assert.match(setupPanel, /QRCode\.toDataURL\(currentSetup\.provisioning_uri/);
  assert.match(setupPanel, /apiFetch<\{ message: string \}>\("\/auth\/2fa\/confirm", \{/);
  assert.match(setupPanel, /body: JSON\.stringify\(\{ code: formData\.get\("code"\) \}\)/);
  assert.match(setupPanel, /router\.push\("\/account"\)/);
  assert.match(setupPanel, /autoComplete="one-time-code"/);

  assert.match(verifyPanel, /const challenge = searchParams\.get\("challenge"\)/);
  assert.match(verifyPanel, /apiFetch<\{ message: string \}>\("\/auth\/2fa\/verify", \{/);
  assert.match(verifyPanel, /challenge_token: challenge/);
  assert.match(verifyPanel, /code: formData\.get\("code"\)/);
  assert.match(verifyPanel, /Missing verification challenge\. Sign in again\./);
  assert.match(verifyPanel, /pending \|\| !challenge/);
  assert.match(verifyPanel, /router\.push\("\/account"\)/);
  assert.match(verifyPanel, /autoComplete="one-time-code"/);

  assert.doesNotMatch(`${setupPanel}\n${verifyPanel}`, /localStorage|sessionStorage|dangerouslySetInnerHTML/);
});

test("account and protected user data flows call authenticated backend endpoints safely", () => {
  const accountPanel = readComponent("AccountPanel");
  const savedJobsPanel = readComponent("SavedJobsPanel");
  const applicationHistoryPanel = readComponent("ApplicationHistoryPanel");

  assert.match(accountPanel, /apiFetch<User>\("\/me"\)/);
  assert.match(accountPanel, /apiFetch<Profile>\("\/me\/profile"\)/);
  assert.match(accountPanel, /apiFetch<Profile>\("\/me\/profile", \{/);
  assert.match(accountPanel, /apiFetch<\{ message: string \}>\("\/auth\/password-change"/);
  assert.match(accountPanel, /apiFetch<\{ message: string \}>\("\/auth\/logout", \{ method: "POST" \}\)/);
  assert.match(accountPanel, /apiFetch<\{ message: string \}>\("\/me", \{/);
  assert.match(accountPanel, /router\.replace\("\/login"\)/);

  assert.match(savedJobsPanel, /apiFetch<SavedJobListResponse>\(`\/saved-jobs\?page=\$\{page\}&page_size=\$\{pageSize\}`\)/);
  assert.match(savedJobsPanel, /apiFetch<\{ message: string \}>\(`\/jobs\/\$\{jobId\}\/save`, \{ method: "DELETE" \}\)/);
  assert.match(savedJobsPanel, /router\.push\("\/login"\)/);

  assert.match(
    applicationHistoryPanel,
    /apiFetch<ApplicationHistoryListResponse>\(`\/application-history\?page=\$\{page\}&page_size=\$\{pageSize\}`\)/
  );
  assert.match(applicationHistoryPanel, /router\.push\("\/login"\)/);
});

test("job browsing and job detail flows cover search, save, draft, interview, and external warning behavior", () => {
  const jobBrowser = readComponent("JobBrowser");
  const jobDetailPanel = readComponent("JobDetailPanel");

  assert.match(jobBrowser, /apiFetch<JobListResponse>\(`\/jobs\?\$\{query\}`\)/);
  assert.match(jobBrowser, /params\.set\("page", String\(page\)\)/);
  assert.match(jobBrowser, /params\.set\("page_size", String\(pageSize\)\)/);
  for (const filter of ["keyword", "company", "location", "category", "source"]) {
    assert.match(jobBrowser, new RegExp(`updateFilter\\("${filter}"`));
  }
  assert.match(jobBrowser, /apiFetch<SavedJob>\(`\/jobs\/\$\{jobId\}\/save`, \{ method: "POST" \}\)/);
  assert.match(jobBrowser, /router\.push\("\/login"\)/);

  assert.match(jobDetailPanel, /apiFetch<JobDetail>\(`\/jobs\/\$\{params\.jobId\}`\)/);
  assert.match(jobDetailPanel, /apiFetch<SavedJob>\(`\/jobs\/\$\{params\.jobId\}\/save`, \{/);
  assert.match(jobDetailPanel, /apiFetch<CoverLetter>\(`\/jobs\/\$\{params\.jobId\}\/cover-letter`, \{/);
  assert.match(jobDetailPanel, /router\.push\(`\/cover-letters\/\$\{draft\.id\}`\)/);
  assert.match(
    jobDetailPanel,
    /apiFetch<InterviewQuestionsResponse>\(`\/jobs\/\$\{params\.jobId\}\/interview-questions`, \{/
  );
  assert.match(jobDetailPanel, /window\.open\(job\.job_url, "_blank", "noopener,noreferrer"\)/);
  assert.match(jobDetailPanel, /job\.external_link_warning/);
  assert.doesNotMatch(jobDetailPanel, /dangerouslySetInnerHTML/);
});

test("resume pages cover list, upload, detail, delete, extraction review, and extraction edit flows", () => {
  const resumeWorkspace = readComponent("ResumeWorkspace");
  const resumeDetailPanel = readComponent("ResumeDetailPanel");
  const extractedProfilePanel = readComponent("ExtractedProfilePanel");

  assert.match(resumeWorkspace, /apiFetch<ResumeListResponse>\("\/resumes"\)/);
  assert.match(resumeWorkspace, /const formData = new FormData\(\)/);
  assert.match(resumeWorkspace, /formData\.set\("file", selectedFile\)/);
  assert.match(resumeWorkspace, /apiFetch<Resume>\("\/resumes", \{/);
  assert.match(
    resumeWorkspace,
    /accept="\.pdf,\.docx,application\/pdf,application\/vnd\.openxmlformats-officedocument\.wordprocessingml\.document"/
  );
  assert.match(resumeWorkspace, /Choose a PDF or DOCX resume to upload\./);
  assert.match(resumeWorkspace, /allowedResumeTypes/);
  assert.match(resumeWorkspace, /maxResumeBytes/);
  assert.match(resumeWorkspace, /router\.push\("\/login"\)/);

  assert.match(resumeDetailPanel, /apiFetch<Resume>\(`\/resumes\/\$\{resumeId\}`\)/);
  assert.match(resumeDetailPanel, /apiFetch<ResumeExtraction>\(`\/resumes\/\$\{resumeId\}\/extraction`\)/);
  assert.match(resumeDetailPanel, /apiFetch<\{ message: string \}>\(`\/resumes\/\$\{resumeId\}`, \{ method: "DELETE" \}\)/);
  assert.match(resumeDetailPanel, /router\.push\("\/resumes"\)/);

  assert.match(extractedProfilePanel, /apiFetch<Resume>\(`\/resumes\/\$\{resumeId\}`\)/);
  assert.match(extractedProfilePanel, /apiFetch<ResumeExtraction>\(`\/resumes\/\$\{resumeId\}\/extraction`\)/);
  assert.match(extractedProfilePanel, /apiFetch<ResumeExtraction>\(`\/resumes\/\$\{resumeId\}\/extraction`, \{/);
  assert.match(extractedProfilePanel, /method: "PATCH"/);
  assert.match(extractedProfilePanel, /router\.push\("\/login"\)/);
});

test("recommendation, cover letter, and application preparation flows use owned-resource endpoints", () => {
  const recommendationsPanel = readComponent("RecommendationsPanel");
  const coverLettersPanel = readComponent("CoverLettersPanel");
  const coverLetterEditor = readComponent("CoverLetterEditor");

  assert.match(
    recommendationsPanel,
    /apiFetch<RecommendationListResponse>\(`\/recommendations\?page=\$\{page\}&page_size=\$\{pageSize\}`\)/
  );
  assert.match(recommendationsPanel, /apiFetch<RecommendationListResponse>\("\/recommendations\/refresh", \{/);
  assert.match(recommendationsPanel, /method: "POST"/);
  assert.match(recommendationsPanel, /apiFetch<CoverLetter>\(`\/jobs\/\$\{jobId\}\/cover-letter`, \{ method: "POST" \}\)/);
  assert.match(recommendationsPanel, /router\.push\(`\/cover-letters\/\$\{draft\.id\}`\)/);
  assert.match(recommendationsPanel, /router\.push\("\/login"\)/);

  assert.match(
    coverLettersPanel,
    /apiFetch<CoverLetterListResponse>\(`\/cover-letters\?page=\$\{page\}&page_size=\$\{pageSize\}`\)/
  );
  assert.match(coverLettersPanel, /router\.push\("\/login"\)/);

  assert.match(coverLetterEditor, /apiFetch<CoverLetter>\(`\/cover-letters\/\$\{params\.coverLetterId\}`\)/);
  assert.match(coverLetterEditor, /apiFetch<CoverLetter>\(`\/cover-letters\/\$\{params\.coverLetterId\}`, \{/);
  assert.match(coverLetterEditor, /method: "PATCH"/);
  assert.match(coverLetterEditor, /router\.push\("\/login"\)/);
  assert.match(coverLetterEditor, /textarea/);
  assert.match(coverLetterEditor, /Draft text must be between 1 and/);
  assert.doesNotMatch(coverLetterEditor, /dangerouslySetInnerHTML/);
});

test("admin dashboard flows call admin-only endpoints and include moderation/audit actions", () => {
  const adminPanel = readComponent("AdminScrapingPanel");
  const adminUserDetailPanel = readComponent("AdminUserDetailPanel");
  const adminRunDetailPanel = readComponent("AdminScrapingRunDetailPanel");

  for (const endpoint of [
    "/admin/health",
    "/admin/users?page=1&page_size=8",
    "/admin/job-sources",
    "/admin/scraping-runs?page=1&page_size=8",
    "/admin/audit-logs?page=1&page_size=10"
  ]) {
    assert.match(adminPanel, new RegExp(`apiFetch<[^>]+>\\("${endpoint.replace(/[/?]/g, "\\$&")}`));
  }
  assert.match(adminPanel, /apiFetch<JobListResponse>\(`\/admin\/jobs\?page=1&page_size=\$\{adminJobPageSize\}`\)/);
  assert.match(adminPanel, /apiFetch<JobListResponse>\(`\/admin\/jobs\?page=\$\{nextPage\}&page_size=\$\{adminJobPageSize\}`\)/);
  assert.match(adminPanel, /apiFetch<AdminJobSource\[]>\("\/admin\/job-sources\/seed", \{ method: "POST" \}\)/);
  assert.match(adminPanel, /apiFetch<ScrapingRun>\("\/admin\/scraping-runs", \{/);
  assert.match(adminPanel, /body: JSON\.stringify\(\{ source_id: source\.id \}\)/);
  assert.match(adminPanel, /apiFetch<User>\(`\/admin\/users\/\$\{target\.id\}`, \{/);
  assert.match(adminPanel, /body: JSON\.stringify\(\{ is_active: isActive \}\)/);
  assert.match(adminPanel, /apiFetch<JobSummary>\(`\/admin\/jobs\/\$\{job\.id\}`, \{/);
  assert.match(adminPanel, /apiFetch<\{ message: string \}>\(`\/admin\/jobs\/\$\{job\.id\}`, \{ method: "DELETE" \}\)/);
  assert.match(adminPanel, /is_suspicious/);
  assert.match(adminPanel, /See more/);
  assert.match(adminPanel, /user\?\.role !== "ADMIN"/);
  assert.match(adminPanel, /Access denied\./);
  assert.match(adminPanel, /\/admin\/audit-logs\?\$\{query\.toString\(\)\}/);
  assert.match(adminPanel, /auditEventOptions/);
  assert.match(adminPanel, /Choose a valid audit event\./);
  assert.match(adminPanel, /Start date must be before end date\./);
  assert.match(adminPanel, /formatAuditAction/);
  assert.match(adminPanel, /formatAuditActor/);
  assert.match(adminPanel, /formatAuditTargetType/);
  assert.doesNotMatch(adminPanel, /risk_engine\.config_update/);
  assert.doesNotMatch(adminPanel, /risk_engine\.admin_access/);
  assert.match(adminPanel, /View Details/);

  assert.match(adminUserDetailPanel, /apiFetch<AdminUserDetail>\(`\/admin\/users\/\$\{params\.userId\}`\)/);
  assert.match(adminRunDetailPanel, /apiFetch<ScrapingRun>\(`\/admin\/scraping-runs\/\$\{params\.runId\}`\)/);
});

test("career roadmap, salary trend, and status pages call their expected read-only endpoints", () => {
  const roleCatalogPanel = readComponent("RoleCatalogPanel");
  const roleDetailPanel = readComponent("RoleDetailPanel");
  const salaryTrendPanel = readComponent("SalaryTrendPanel");
  const statusPage = readPage("status");

  assert.match(roleCatalogPanel, /apiFetch<JobRoleListResponse>\("\/job-roles"\)/);
  assert.match(roleDetailPanel, /apiFetch<JobRoleDetail>\(`\/job-roles\/\$\{encodeURIComponent\(slug\)\}`\)/);
  assert.match(salaryTrendPanel, /apiFetch<SalaryTrendResponse>\(\s*`\/salary-trends\?/);
  assert.match(salaryTrendPanel, /Choose a valid month range\./);
  assert.match(salaryTrendPanel, /\\p\{L\}\\p\{N\}/);
  assert.match(statusPage, /getApiBaseUrl\(\)/);
});

test("job search and upload surfaces include client-side input constraints", () => {
  const jobBrowser = readComponent("JobBrowser");
  const resumeWorkspace = readComponent("ResumeWorkspace");

  assert.match(jobBrowser, /searchPattern/);
  assert.match(jobBrowser, /Search fields can use letters, numbers, spaces, and common punctuation only\./);
  assert.match(jobBrowser, /\\p\{L\}\\p\{N\}/);
  assert.match(resumeWorkspace, /Upload a valid PDF or DOCX resume\./);
  assert.match(resumeWorkspace, /Resume must be larger than 0 bytes/);
});

test("frontend security guardrails avoid unsafe HTML rendering and browser token storage", () => {
  const sourceFiles = [
    "AccountPanel",
    "AdminScrapingPanel",
    "ApplicationHistoryPanel",
    "CoverLetterEditor",
    "CoverLettersPanel",
    "ExtractedProfilePanel",
    "HomeHub",
    "JobBrowser",
    "JobDetailPanel",
    "RecommendationsPanel",
    "ResumeDetailPanel",
    "ResumeWorkspace",
    "SavedJobsPanel"
  ].map(readComponent).join("\n");

  assert.doesNotMatch(sourceFiles, /dangerouslySetInnerHTML/);
  assert.doesNotMatch(sourceFiles, /localStorage|sessionStorage/);
  assert.match(readProjectFile("src", "lib", "api.ts"), /credentials: "include"/);
  assert.match(readProjectFile("src", "lib", "api.ts"), /cache: "no-store"/);
});
