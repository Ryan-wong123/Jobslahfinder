"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  apiFetch,
  formatDate,
  formatDateTime,
  type AdminAuditLog,
  type AdminAuditLogListResponse,
  type AdminHealth,
  type AdminJobSource,
  type AdminUserDetail,
  type AdminUserListResponse,
  type JobListResponse,
  type JobSummary,
  type ScrapingRun,
  type User
} from "@/lib/api";
import { FormMessage } from "./FormControls";

type SourceActionState = Record<number, boolean>;
type UserActionState = Record<number, boolean>;
type JobActionState = Record<number, boolean>;
const adminJobPageSize = 8;
const trackedPortalNames = ["JobStreet", "MyCareersFuture", "JobsLah", "FastJobs"] as const;
const auditEventOptions = [
  { value: "auth.2fa_setup", label: "2FA setup" },
  { value: "auth.2fa_verify", label: "2FA verification" },
  { value: "auth.login", label: "Login" },
  { value: "auth.logout", label: "Logout" },
  { value: "auth.password_change", label: "Password change" },
  { value: "auth.password_reset_request", label: "Password reset request" },
  { value: "auth.password_reset_confirm", label: "Password reset complete" },
  { value: "account.update", label: "Account update" },
  { value: "account.profile_update", label: "Profile update" },
  { value: "account.deletion_request", label: "Account deletion request" },
  { value: "account.deletion", label: "Account deletion" },
  { value: "authorization.denied", label: "Access denied" },
  { value: "admin.user.update", label: "Admin user update" },
  { value: "admin.job.update", label: "Admin job update" },
  { value: "admin.job.delete", label: "Admin job delete" },
  { value: "admin.scraping_run.trigger", label: "Scraping run triggered" }
] as const;
const auditEventValues = new Set<string>(auditEventOptions.map((option) => option.value));

function statusClass(status: string): string {
  if (status === "SUCCESS" || status === "ok") {
    return "border-teal-200 bg-teal-50 text-teal-800";
  }
  if (status === "FAILED" || status === "FAILURE" || status === "DENIED") {
    return "border-red-200 bg-red-50 text-red-700";
  }
  return "border-zinc-200 bg-zinc-50 text-zinc-700";
}

function pill(label: string, tone: string) {
  return <span className={`rounded border px-2 py-1 text-xs font-medium ${statusClass(tone)}`}>{label}</span>;
}

function formatAuditEventLabel(eventType: string): string {
  return eventType
    .split(".")
    .map((part) => part.replace(/_/g, " "))
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatAuditDetailKey(key: string): string {
  return key
    .replace(/_/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function formatAuditTargetType(targetType: string): string {
  return targetType.replace(/_/g, " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

function isAuditDetailObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function auditValueToText(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "None";
  }
  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
  }
  if (Array.isArray(value)) {
    return value.map((item) => auditValueToText(item)).join(", ");
  }
  if (isAuditDetailObject(value)) {
    return Object.entries(value)
      .map(([key, nestedValue]) => `${formatAuditDetailKey(key)}: ${auditValueToText(nestedValue)}`)
      .join(", ");
  }
  return String(value);
}

function formatAuditActor(log: AdminAuditLog): string {
  const adminEmail = log.details_json?.admin_email;
  if (typeof adminEmail === "string" && adminEmail) {
    return adminEmail;
  }
  if (log.user_id) {
    return `User ${log.user_id}`;
  }
  return "System";
}

function formatAuditTarget(log: AdminAuditLog): string {
  if (!log.target_type) {
    return "Platform";
  }
  const targetType = formatAuditTargetType(log.target_type);
  return log.target_id ? `${targetType} #${log.target_id}` : targetType;
}

function formatAuditAction(log: AdminAuditLog): string {
  if (log.event_type === "authorization.denied") {
    return "Access denied";
  }
  if (log.event_type === "account.update") {
    return "Account updated";
  }
  if (log.event_type === "account.profile_update") {
    return "Profile updated";
  }
  if (log.event_type.startsWith("auth.")) {
    return formatAuditEventLabel(log.event_type.replace("auth.", ""));
  }
  if (log.event_type.startsWith("admin.")) {
    return formatAuditEventLabel(log.event_type.replace("admin.", ""));
  }
  return formatAuditEventLabel(log.event_type);
}

function auditContextItems(log: AdminAuditLog): Array<{ label: string; value: string }> {
  const details = log.details_json ?? {};
  const hiddenKeys = new Set(["admin_email", "admin_role", "auth_source", "change_count", "changes"]);
  const items = Object.entries(details)
    .filter(([key, value]) => !hiddenKeys.has(key) && value !== null && value !== undefined && value !== "")
    .map(([key, value]) => ({ label: formatAuditDetailKey(key), value: auditValueToText(value) }));

  if (log.details_json?.admin_role && typeof log.details_json.admin_role === "string") {
    items.unshift({ label: "Role", value: log.details_json.admin_role });
  }
  return items;
}

function auditChangeSummaries(details: Record<string, unknown> | null): string[] {
  const changes = details?.changes;
  if (!Array.isArray(changes)) {
    return [];
  }
  return changes
    .map((change) => {
      if (isAuditDetailObject(change) && typeof change.summary === "string") {
        return change.summary;
      }
      return auditValueToText(change);
    })
    .filter(Boolean)
    .slice(0, 5);
}

function AuditDetails({ log }: { log: AdminAuditLog }) {
  const contextItems = auditContextItems(log);
  const changeSummaries = auditChangeSummaries(log.details_json);
  if (contextItems.length === 0 && changeSummaries.length === 0) {
    return null;
  }

  return (
    <details className="group rounded border border-zinc-200 bg-white">
      <summary className="cursor-pointer list-none px-3 py-2 text-xs font-medium text-zinc-700 transition hover:bg-zinc-50">
        <span className="inline-flex items-center gap-2">
          <span className="text-zinc-950">View Details</span>
          <span className="text-zinc-400 group-open:hidden">+</span>
          <span className="hidden text-zinc-400 group-open:inline">-</span>
        </span>
      </summary>
      <div className="grid gap-3 border-t border-zinc-200 bg-zinc-50 p-3">
        {changeSummaries.length ? (
          <ul className="grid gap-1 text-xs text-zinc-700">
            {changeSummaries.map((summary, index) => (
              <li key={`${summary}-${index}`} className="rounded border border-zinc-200 bg-white px-2 py-1">
                {summary}
              </li>
            ))}
          </ul>
        ) : null}
        {contextItems.length ? (
          <dl className="grid gap-2 sm:grid-cols-2">
            {contextItems.slice(0, 6).map((item) => (
              <div key={item.label} className="min-w-0">
                <dt className="text-[11px] font-medium uppercase text-zinc-500">{item.label}</dt>
                <dd className="mt-0.5 truncate text-xs text-zinc-800" title={item.value}>{item.value}</dd>
              </div>
            ))}
          </dl>
        ) : null}
      </div>
    </details>
  );
}

async function fetchJobsThroughPage(page: number) {
  const firstPage = await apiFetch<JobListResponse>(`/admin/jobs?page=1&page_size=${adminJobPageSize}`);
  if (page <= 1) {
    return firstPage;
  }

  const nextPages = await Promise.all(
    Array.from({ length: page - 1 }, (_, index) =>
      apiFetch<JobListResponse>(`/admin/jobs?page=${index + 2}&page_size=${adminJobPageSize}`)
    )
  );

  return {
    ...firstPage,
    items: [firstPage, ...nextPages].flatMap((response) => response.items),
    page,
    total: nextPages.at(-1)?.total ?? firstPage.total
  };
}

async function fetchAdminData(targetJobPage = 1) {
  const [currentUser, currentHealth, currentUsers, currentJobs, currentSources, currentRuns, currentAuditLogs] =
    await Promise.all([
      apiFetch<User>("/me"),
      apiFetch<AdminHealth>("/admin/health"),
      apiFetch<AdminUserListResponse>("/admin/users?page=1&page_size=8"),
      fetchJobsThroughPage(targetJobPage),
      apiFetch<AdminJobSource[]>("/admin/job-sources"),
      apiFetch<ScrapingRun[]>("/admin/scraping-runs?page=1&page_size=8"),
      apiFetch<AdminAuditLogListResponse>("/admin/audit-logs?page=1&page_size=10")
    ]);
  return { currentUser, currentHealth, currentUsers, currentJobs, currentSources, currentRuns, currentAuditLogs };
}

export function AdminScrapingPanel() {
  const [user, setUser] = useState<User | null>(null);
  const [health, setHealth] = useState<AdminHealth | null>(null);
  const [users, setUsers] = useState<AdminUserListResponse | null>(null);
  const [jobs, setJobs] = useState<JobListResponse | null>(null);
  const [sources, setSources] = useState<AdminJobSource[]>([]);
  const [runs, setRuns] = useState<ScrapingRun[]>([]);
  const [auditLogs, setAuditLogs] = useState<AdminAuditLogListResponse | null>(null);
  const [selectedUser, setSelectedUser] = useState<AdminUserDetail | null>(null);
  const [selectedRun, setSelectedRun] = useState<ScrapingRun | null>(null);
  const [auditEventFilter, setAuditEventFilter] = useState("");
  const [auditOutcomeFilter, setAuditOutcomeFilter] = useState("");
  const [auditFromFilter, setAuditFromFilter] = useState("");
  const [auditToFilter, setAuditToFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [seeding, setSeeding] = useState(false);
  const [loadingMoreJobs, setLoadingMoreJobs] = useState(false);
  const [jobPage, setJobPage] = useState(1);
  const [runningBySource, setRunningBySource] = useState<SourceActionState>({});
  const [updatingUser, setUpdatingUser] = useState<UserActionState>({});
  const [updatingJob, setUpdatingJob] = useState<JobActionState>({});
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const sourceNames = useMemo(() => {
    return new Map(sources.map((source) => [source.id, source.source_name]));
  }, [sources]);

  const portalJobCounts = useMemo(() => {
    const countsBySourceName = new Map(sources.map((source) => [source.source_name, source.job_count]));
    return trackedPortalNames.map((sourceName) => ({
      sourceName,
      jobCount: countsBySourceName.get(sourceName) ?? 0
    }));
  }, [sources]);

  async function refreshAdminData() {
    const data = await fetchAdminData(jobPage);
    setUser(data.currentUser);
    setHealth(data.currentHealth);
    setUsers(data.currentUsers);
    setJobs(data.currentJobs);
    setSources(data.currentSources);
    setRuns(data.currentRuns);
    setAuditLogs(data.currentAuditLogs);
  }

  useEffect(() => {
    let active = true;
    fetchAdminData()
      .then((data) => {
        if (active) {
          setUser(data.currentUser);
          setHealth(data.currentHealth);
          setUsers(data.currentUsers);
          setJobs(data.currentJobs);
          setSources(data.currentSources);
          setRuns(data.currentRuns);
          setAuditLogs(data.currentAuditLogs);
        }
      })
      .catch((caught) => {
        if (active) {
          setError(caught instanceof Error ? caught.message : "Unable to load admin dashboard.");
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, []);

  async function seedSources() {
    setSeeding(true);
    setMessage(null);
    setError(null);
    try {
      await apiFetch<AdminJobSource[]>("/admin/job-sources/seed", { method: "POST" });
      await refreshAdminData();
      setMessage("Approved job sources are ready.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to prepare job sources.");
    } finally {
      setSeeding(false);
    }
  }

  async function runScrape(source: AdminJobSource) {
    setRunningBySource((current) => ({ ...current, [source.id]: true }));
    setMessage(null);
    setError(null);
    try {
      const run = await apiFetch<ScrapingRun>("/admin/scraping-runs", {
        method: "POST",
        body: JSON.stringify({ source_id: source.id })
      });
      await refreshAdminData();
      setMessage(`${source.source_name} scrape finished with ${run.jobs_retrieved} job(s) stored.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to run scrape.");
    } finally {
      setRunningBySource((current) => ({ ...current, [source.id]: false }));
    }
  }

  async function setUserActive(target: User, isActive: boolean) {
    setUpdatingUser((current) => ({ ...current, [target.id]: true }));
    setMessage(null);
    setError(null);
    try {
      await apiFetch<User>(`/admin/users/${target.id}`, {
        method: "PATCH",
        body: JSON.stringify({ is_active: isActive })
      });
      await refreshAdminData();
      setMessage(`${target.email} ${isActive ? "activated" : "deactivated"}.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to update user.");
    } finally {
      setUpdatingUser((current) => ({ ...current, [target.id]: false }));
    }
  }

  async function updateJob(job: JobSummary, body: { is_active?: boolean; is_suspicious?: boolean }) {
    setUpdatingJob((current) => ({ ...current, [job.id]: true }));
    setMessage(null);
    setError(null);
    try {
      await apiFetch<JobSummary>(`/admin/jobs/${job.id}`, {
        method: "PATCH",
        body: JSON.stringify(body)
      });
      await refreshAdminData();
      setMessage("Job moderation updated.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to update job.");
    } finally {
      setUpdatingJob((current) => ({ ...current, [job.id]: false }));
    }
  }

  async function deleteJob(job: JobSummary) {
    const confirmed = window.confirm(`Delete "${job.title}" from the platform? This cannot be undone.`);
    if (!confirmed) {
      return;
    }
    setUpdatingJob((current) => ({ ...current, [job.id]: true }));
    setMessage(null);
    setError(null);
    try {
      await apiFetch<{ message: string }>(`/admin/jobs/${job.id}`, { method: "DELETE" });
      await refreshAdminData();
      setMessage("Job deleted.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to delete job.");
    } finally {
      setUpdatingJob((current) => ({ ...current, [job.id]: false }));
    }
  }

  async function loadMoreJobs() {
    if (!jobs || jobs.items.length >= jobs.total) {
      return;
    }
    const nextPage = jobPage + 1;
    setLoadingMoreJobs(true);
    setMessage(null);
    setError(null);
    try {
      const nextJobs = await apiFetch<JobListResponse>(`/admin/jobs?page=${nextPage}&page_size=${adminJobPageSize}`);
      setJobs((current) => {
        if (!current) {
          return nextJobs;
        }
        return {
          ...nextJobs,
          items: [...current.items, ...nextJobs.items],
          page: nextPage
        };
      });
      setJobPage(nextPage);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to load more jobs.");
    } finally {
      setLoadingMoreJobs(false);
    }
  }

  async function loadUserDetail(target: User) {
    setMessage(null);
    setError(null);
    try {
      setSelectedUser(await apiFetch<AdminUserDetail>(`/admin/users/${target.id}`));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to load user details.");
    }
  }

  async function loadRunDetail(run: ScrapingRun) {
    setMessage(null);
    setError(null);
    try {
      setSelectedRun(await apiFetch<ScrapingRun>(`/admin/scraping-runs/${run.id}`));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to load scraping run details.");
    }
  }

  async function applyAuditFilters() {
    setMessage(null);
    setError(null);
    const eventFilter = auditEventFilter.trim();
    if (eventFilter && !auditEventValues.has(eventFilter)) {
      setError("Choose a valid audit event.");
      return;
    }
    if (auditOutcomeFilter && !["SUCCESS", "FAILURE", "DENIED"].includes(auditOutcomeFilter)) {
      setError("Choose a valid audit outcome.");
      return;
    }
    if (auditFromFilter && Number.isNaN(new Date(auditFromFilter).getTime())) {
      setError("Choose a valid start date.");
      return;
    }
    if (auditToFilter && Number.isNaN(new Date(auditToFilter).getTime())) {
      setError("Choose a valid end date.");
      return;
    }
    if (auditFromFilter && auditToFilter && new Date(auditFromFilter) > new Date(auditToFilter)) {
      setError("Start date must be before end date.");
      return;
    }
    const query = new URLSearchParams({ page: "1", page_size: "10" });
    if (eventFilter) {
      query.set("event_type", eventFilter);
    }
    if (auditOutcomeFilter) {
      query.set("outcome", auditOutcomeFilter);
    }
    if (auditFromFilter) {
      query.set("created_from", new Date(auditFromFilter).toISOString());
    }
    if (auditToFilter) {
      query.set("created_to", new Date(auditToFilter).toISOString());
    }
    try {
      setAuditLogs(await apiFetch<AdminAuditLogListResponse>(`/admin/audit-logs?${query.toString()}`));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to filter audit logs.");
    }
  }

  if (loading) {
    return <p className="text-sm text-zinc-600">Loading admin dashboard...</p>;
  }

  if (user?.role !== "ADMIN") {
    return (
      <section className="rounded border border-zinc-200 bg-white p-6 shadow-sm">
        <h1 className="text-2xl font-semibold text-zinc-950">Admin</h1>
        <p className="mt-2 text-sm text-zinc-600">Access denied.</p>
        <Link className="mt-5 inline-block rounded bg-zinc-950 px-4 py-2 text-sm font-medium text-white" href="/">
          Back home
        </Link>
      </section>
    );
  }

  return (
    <div className="space-y-6">
      <section className="rounded border border-zinc-200 bg-white p-6 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold text-zinc-950">Admin Dashboard</h1>
            <p className="mt-1 text-sm text-zinc-600">Manage users, moderate jobs, inspect scraping runs, and review audit metadata.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link className="rounded border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-900 hover:bg-zinc-100" href="/jobs">
              View jobs
            </Link>
            <a className="rounded bg-zinc-950 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-800" href="/risk-engine/admin/dashboard">
              Risk Engine
            </a>
          </div>
        </div>
        <div className="mt-5 grid gap-3 md:grid-cols-5">
          <div className="rounded border border-zinc-200 p-4">
            <p className="text-xs uppercase text-zinc-500">Health</p>
            <p className="mt-2">{health ? pill(health.status, health.status) : "Unknown"}</p>
            <p className="mt-2 text-xs text-zinc-500">
              DB {health?.database?.status ?? "unknown"} / Redis {health?.redis?.status ?? "unknown"} / Worker {health?.worker?.status ?? "unknown"}
            </p>
          </div>
          <div className="rounded border border-zinc-200 p-4">
            <p className="text-xs uppercase text-zinc-500">Users</p>
            <p className="mt-2 text-xl font-semibold">{users?.total ?? 0}</p>
          </div>
          <div className="rounded border border-zinc-200 p-4">
            <p className="text-xs uppercase text-zinc-500">Jobs</p>
            <p className="mt-2 text-xl font-semibold">{jobs?.total ?? 0}</p>
            <dl className="mt-2 space-y-1 text-xs text-zinc-600">
              {portalJobCounts.map((portal) => (
                <div key={portal.sourceName} className="flex items-center justify-between gap-2">
                  <dt>{portal.sourceName}</dt>
                  <dd className="text-sm font-semibold text-zinc-950">{portal.jobCount}</dd>
                </div>
              ))}
            </dl>
          </div>
          <div className="rounded border border-zinc-200 p-4">
            <p className="text-xs uppercase text-zinc-500">Runs</p>
            <p className="mt-2 text-xl font-semibold">{runs.length}</p>
          </div>
          <div className="rounded border border-zinc-200 p-4">
            <p className="text-xs uppercase text-zinc-500">Audit</p>
            <p className="mt-2 text-xl font-semibold">{auditLogs?.total ?? 0}</p>
          </div>
        </div>
        <FormMessage message={message} tone="success" />
        <FormMessage message={error} tone="error" />
      </section>

      <section className="rounded border border-zinc-200 bg-white p-6 shadow-sm">
        <h2 className="text-lg font-semibold text-zinc-950">Users</h2>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[720px] border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-zinc-200 text-xs uppercase text-zinc-500">
                <th className="py-3 pr-4 font-medium">Email</th>
                <th className="py-3 pr-4 font-medium">Role</th>
                <th className="py-3 pr-4 font-medium">Status</th>
                <th className="py-3 pr-4 font-medium">Created</th>
                <th className="py-3 pr-4 font-medium">Last login</th>
                <th className="py-3 font-medium">Action</th>
              </tr>
            </thead>
            <tbody>
              {users?.items.length ? (
                users.items.map((item) => (
                  <tr key={item.id} className="border-b border-zinc-100">
                    <td className="py-3 pr-4 text-zinc-950">{item.email}</td>
                    <td className="py-3 pr-4 text-zinc-700">{item.role}</td>
                    <td className="py-3 pr-4">{pill(item.is_active ? "Active" : "Inactive", item.is_active ? "SUCCESS" : "FAILED")}</td>
                    <td className="py-3 pr-4 text-zinc-700">{formatDateTime(item.created_at)}</td>
                    <td className="py-3 pr-4 text-zinc-700">{formatDateTime(item.last_login_at)}</td>
                    <td className="py-3">
                      <button
                        className="rounded border border-zinc-300 px-3 py-2 text-sm font-medium text-zinc-900 disabled:cursor-not-allowed disabled:text-zinc-400"
                        disabled={item.id === user.id || Boolean(updatingUser[item.id])}
                        onClick={() => setUserActive(item, !item.is_active)}
                        type="button"
                      >
                        {item.is_active ? "Deactivate" : "Activate"}
                      </button>
                      <button
                        className="ml-2 rounded border border-zinc-300 px-3 py-2 text-sm font-medium text-zinc-900"
                        onClick={() => loadUserDetail(item)}
                        type="button"
                      >
                        Details
                      </button>
                      <Link
                        className="ml-2 rounded border border-zinc-300 px-3 py-2 text-sm font-medium text-zinc-900"
                        href={`/admin/users/${item.id}`}
                      >
                        Page
                      </Link>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td className="py-4 text-zinc-600" colSpan={6}>No users found.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        {selectedUser ? (
          <div className="mt-4 rounded border border-zinc-200 bg-zinc-50 p-4 text-sm text-zinc-700">
            <p className="font-medium text-zinc-950">{selectedUser.email}</p>
            <p className="mt-1">Updated {formatDateTime(selectedUser.updated_at)}</p>
            <p className="mt-1">
              Resumes {selectedUser.resume_count} / Saved jobs {selectedUser.saved_job_count} / Recommendations {selectedUser.recommendation_count} / Cover letters {selectedUser.cover_letter_count} / History {selectedUser.application_history_count}
            </p>
          </div>
        ) : null}
      </section>

      <section className="rounded border border-zinc-200 bg-white p-6 shadow-sm">
        <h2 className="text-lg font-semibold text-zinc-950">Jobs</h2>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[860px] border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-zinc-200 text-xs uppercase text-zinc-500">
                <th className="py-3 pr-4 font-medium">Title</th>
                <th className="py-3 pr-4 font-medium">Company</th>
                <th className="py-3 pr-4 font-medium">Source</th>
                <th className="py-3 pr-4 font-medium">Posted</th>
                <th className="py-3 pr-4 font-medium">Flags</th>
                <th className="py-3 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {jobs?.items.length ? (
                jobs.items.map((job) => (
                  <tr key={job.id} className="border-b border-zinc-100">
                    <td className="py-3 pr-4 text-zinc-950">{job.title}</td>
                    <td className="py-3 pr-4 text-zinc-700">{job.company}</td>
                    <td className="py-3 pr-4 text-zinc-700">{job.source.source_name}</td>
                    <td className="py-3 pr-4 text-zinc-700">{formatDate(job.posting_date)}</td>
                    <td className="space-x-2 py-3 pr-4">
                      {pill(job.is_active ? "Active" : "Disabled", job.is_active ? "SUCCESS" : "FAILED")}
                      {job.is_suspicious ? pill("Suspicious", "FAILED") : pill("Reviewed", "SUCCESS")}
                    </td>
                    <td className="py-3">
                      <div className="grid w-28 gap-2">
                        <button
                          className="rounded border border-zinc-300 px-3 py-2 text-sm font-medium text-zinc-900 disabled:cursor-not-allowed disabled:text-zinc-400"
                          disabled={Boolean(updatingJob[job.id])}
                          onClick={() => updateJob(job, { is_active: !job.is_active })}
                          type="button"
                        >
                          {job.is_active ? "Disable" : "Enable"}
                        </button>
                        <button
                          className="rounded border border-zinc-300 px-3 py-2 text-sm font-medium text-zinc-900 disabled:cursor-not-allowed disabled:text-zinc-400"
                          disabled={Boolean(updatingJob[job.id])}
                          onClick={() => updateJob(job, { is_suspicious: !job.is_suspicious })}
                          type="button"
                        >
                          {job.is_suspicious ? "Clear flag" : "Flag"}
                        </button>
                        <button
                          className="rounded border border-red-300 px-3 py-2 text-sm font-medium text-red-700 disabled:cursor-not-allowed disabled:text-zinc-400"
                          disabled={Boolean(updatingJob[job.id])}
                          onClick={() => deleteJob(job)}
                          type="button"
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td className="py-4 text-zinc-600" colSpan={6}>No jobs found.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        {jobs && jobs.items.length < jobs.total ? (
          <div className="mt-4 flex items-center justify-between gap-3">
            <p className="text-sm text-zinc-600">
              Showing {jobs.items.length} of {jobs.total} scraped jobs.
            </p>
            <button
              className="rounded border border-zinc-300 bg-white px-4 py-2 text-sm font-medium text-zinc-900 transition hover:bg-zinc-100 disabled:cursor-not-allowed disabled:text-zinc-400"
              disabled={loadingMoreJobs}
              onClick={loadMoreJobs}
              type="button"
            >
              {loadingMoreJobs ? "Loading..." : "See more"}
            </button>
          </div>
        ) : jobs && jobs.total > 0 ? (
          <p className="mt-4 text-sm text-zinc-600">Showing all {jobs.total} scraped jobs.</p>
        ) : null}
      </section>

      <section className="rounded border border-zinc-200 bg-white p-6 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-lg font-semibold text-zinc-950">Scraping</h2>
          <button
            className="rounded bg-zinc-950 px-4 py-2 text-sm font-medium text-white transition hover:bg-zinc-800 disabled:cursor-not-allowed disabled:bg-zinc-400"
            disabled={seeding}
            onClick={seedSources}
            type="button"
          >
            {seeding ? "Preparing..." : "Prepare approved sources"}
          </button>
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          {sources.length === 0 ? (
            <p className="text-sm text-zinc-600">No sources yet.</p>
          ) : (
            sources.map((source) => (
              <div key={source.id} className="rounded border border-zinc-200 p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="font-medium text-zinc-950">{source.source_name}</p>
                    <p className="mt-1 break-all text-sm text-zinc-600">{source.base_url}</p>
                    <p className="mt-1 text-xs text-zinc-500">{source.is_enabled ? "Enabled" : "Disabled"}</p>
                  </div>
                  <button
                    className="rounded bg-teal-700 px-3 py-2 text-sm font-medium text-white transition hover:bg-teal-800 disabled:cursor-not-allowed disabled:bg-zinc-300"
                    disabled={!source.is_enabled || Boolean(runningBySource[source.id])}
                    onClick={() => runScrape(source)}
                    type="button"
                  >
                    {runningBySource[source.id] ? "Running..." : "Run"}
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
        <div className="mt-5 overflow-x-auto">
          <table className="w-full min-w-[680px] border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-zinc-200 text-xs uppercase text-zinc-500">
                <th className="py-3 pr-4 font-medium">Source</th>
                <th className="py-3 pr-4 font-medium">Status</th>
                <th className="py-3 pr-4 font-medium">Jobs</th>
                <th className="py-3 pr-4 font-medium">Started</th>
                <th className="py-3 pr-4 font-medium">Completed</th>
                <th className="py-3 font-medium">Error</th>
                <th className="py-3 pl-4 font-medium">Action</th>
              </tr>
            </thead>
            <tbody>
              {runs.length === 0 ? (
                <tr>
                  <td className="py-4 text-zinc-600" colSpan={7}>No scraping runs yet.</td>
                </tr>
              ) : (
                runs.map((run) => (
                  <tr key={run.id} className="border-b border-zinc-100">
                    <td className="py-3 pr-4 text-zinc-950">{sourceNames.get(run.source_id) ?? `Source ${run.source_id}`}</td>
                    <td className="py-3 pr-4">{pill(run.status, run.status)}</td>
                    <td className="py-3 pr-4 text-zinc-700">{run.jobs_retrieved}</td>
                    <td className="py-3 pr-4 text-zinc-700">{formatDateTime(run.started_at)}</td>
                    <td className="py-3 pr-4 text-zinc-700">{formatDateTime(run.completed_at)}</td>
                    <td className="py-3 text-zinc-600">{run.error_message ?? "None"}</td>
                    <td className="py-3 pl-4">
                      <button
                        className="rounded border border-zinc-300 px-3 py-2 text-sm font-medium text-zinc-900"
                        onClick={() => loadRunDetail(run)}
                        type="button"
                      >
                        Details
                      </button>
                      <Link
                        className="ml-2 rounded border border-zinc-300 px-3 py-2 text-sm font-medium text-zinc-900"
                        href={`/admin/scraping-runs/${run.id}`}
                      >
                        Page
                      </Link>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        {selectedRun ? (
          <div className="mt-4 rounded border border-zinc-200 bg-zinc-50 p-4 text-sm text-zinc-700">
            <p className="font-medium text-zinc-950">Run {selectedRun.id}</p>
            <p className="mt-1">Source {sourceNames.get(selectedRun.source_id) ?? selectedRun.source_id}</p>
            <p className="mt-1">
              Status {selectedRun.status}, jobs {selectedRun.jobs_retrieved}, started {formatDateTime(selectedRun.started_at)}, completed {formatDateTime(selectedRun.completed_at)}
            </p>
            <p className="mt-1">Error: {selectedRun.error_message ?? "None"}</p>
          </div>
        ) : null}
      </section>

      <section className="rounded border border-zinc-200 bg-white p-6 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-zinc-950">Audit Logs</h2>
            <p className="mt-1 text-sm text-zinc-600">{auditLogs?.total ?? 0} security event(s) found.</p>
          </div>
          {auditLogs?.items.length ? (
            <span className="rounded border border-zinc-200 bg-zinc-50 px-3 py-2 text-xs font-medium text-zinc-600">
              Latest {auditLogs.items.length}
            </span>
          ) : null}
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-[1.2fr_1fr_1fr_1fr_auto]">
          <label className="grid gap-1 text-xs font-medium uppercase text-zinc-500">
            Event
            <select
              className="rounded border border-zinc-300 px-3 py-2 text-sm font-normal normal-case text-zinc-950"
              onChange={(event) => setAuditEventFilter(event.target.value)}
              value={auditEventFilter}
            >
              <option value="">Any event</option>
              {auditEventOptions.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </label>
          <label className="grid gap-1 text-xs font-medium uppercase text-zinc-500">
            Outcome
            <select
              className="rounded border border-zinc-300 px-3 py-2 text-sm font-normal normal-case text-zinc-950"
              onChange={(event) => setAuditOutcomeFilter(event.target.value)}
              value={auditOutcomeFilter}
            >
              <option value="">Any outcome</option>
              <option value="SUCCESS">SUCCESS</option>
              <option value="FAILURE">FAILURE</option>
              <option value="DENIED">DENIED</option>
            </select>
          </label>
          <label className="grid gap-1 text-xs font-medium uppercase text-zinc-500">
            From
            <input
              className="rounded border border-zinc-300 px-3 py-2 text-sm font-normal normal-case text-zinc-950"
              onChange={(event) => setAuditFromFilter(event.target.value)}
              type="datetime-local"
              value={auditFromFilter}
            />
          </label>
          <label className="grid gap-1 text-xs font-medium uppercase text-zinc-500">
            To
            <input
              className="rounded border border-zinc-300 px-3 py-2 text-sm font-normal normal-case text-zinc-950"
              onChange={(event) => setAuditToFilter(event.target.value)}
              type="datetime-local"
              value={auditToFilter}
            />
          </label>
          <button
            className="self-end rounded bg-zinc-950 px-5 py-2 text-sm font-medium text-white transition hover:bg-zinc-800"
            onClick={applyAuditFilters}
            type="button"
          >
            Filter
          </button>
        </div>
        <div className="mt-5 overflow-x-auto rounded border border-zinc-200">
          <table className="w-full min-w-[760px] border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-zinc-200 bg-zinc-50 text-xs uppercase text-zinc-500">
                <th className="px-4 py-3 font-medium">Action</th>
                <th className="px-4 py-3 font-medium">Outcome</th>
                <th className="px-4 py-3 font-medium">Actor</th>
                <th className="px-4 py-3 font-medium">Target</th>
                <th className="px-4 py-3 font-medium">When</th>
              </tr>
            </thead>
            <tbody>
              {auditLogs?.items.length ? (
                auditLogs.items.map((log) => (
                  <tr key={log.id} className="border-b border-zinc-100 align-top last:border-b-0 hover:bg-zinc-50/70">
                    <td className="px-4 py-4">
                      <div className="min-w-0">
                        <p className="font-medium text-zinc-950">{formatAuditAction(log)}</p>
                        <p className="mt-1 break-words text-xs text-zinc-500">{log.event_type}</p>
                        <div className="mt-3">
                          <AuditDetails log={log} />
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-4">{pill(log.outcome, log.outcome)}</td>
                    <td className="px-4 py-4">
                      <span className="block max-w-40 truncate text-zinc-800" title={formatAuditActor(log)}>
                        {formatAuditActor(log)}
                      </span>
                    </td>
                    <td className="px-4 py-4">
                      <span className="block max-w-36 truncate text-zinc-800" title={formatAuditTarget(log)}>
                        {formatAuditTarget(log)}
                      </span>
                      <span className="mt-1 block text-xs text-zinc-500">Record #{log.id}</span>
                    </td>
                    <td className="whitespace-nowrap px-4 py-4 text-zinc-700">{formatDateTime(log.created_at)}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td className="px-4 py-6 text-zinc-600" colSpan={5}>No audit logs found.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
