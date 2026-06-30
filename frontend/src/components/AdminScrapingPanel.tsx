"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  apiFetch,
  formatDate,
  formatDateTime,
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
  const [runningBySource, setRunningBySource] = useState<SourceActionState>({});
  const [updatingUser, setUpdatingUser] = useState<UserActionState>({});
  const [updatingJob, setUpdatingJob] = useState<JobActionState>({});
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const sourceNames = useMemo(() => {
    return new Map(sources.map((source) => [source.id, source.source_name]));
  }, [sources]);

  async function fetchAdminData() {
    const [currentUser, currentHealth, currentUsers, currentJobs, currentSources, currentRuns, currentAuditLogs] =
      await Promise.all([
        apiFetch<User>("/me"),
        apiFetch<AdminHealth>("/admin/health"),
        apiFetch<AdminUserListResponse>("/admin/users?page=1&page_size=8"),
        apiFetch<JobListResponse>("/admin/jobs?page=1&page_size=8"),
        apiFetch<AdminJobSource[]>("/admin/job-sources"),
        apiFetch<ScrapingRun[]>("/admin/scraping-runs?page=1&page_size=8"),
        apiFetch<AdminAuditLogListResponse>("/admin/audit-logs?page=1&page_size=10")
      ]);
    return { currentUser, currentHealth, currentUsers, currentJobs, currentSources, currentRuns, currentAuditLogs };
  }

  async function refreshAdminData() {
    const data = await fetchAdminData();
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
    const query = new URLSearchParams({ page: "1", page_size: "10" });
    if (auditEventFilter.trim()) {
      query.set("event_type", auditEventFilter.trim());
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
          <Link className="rounded border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-900 hover:bg-zinc-100" href="/jobs">
            View jobs
          </Link>
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
                    <td className="flex flex-wrap gap-2 py-3">
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
        <h2 className="text-lg font-semibold text-zinc-950">Audit Logs</h2>
        <div className="mt-4 grid gap-3 md:grid-cols-5">
          <input
            className="rounded border border-zinc-300 px-3 py-2 text-sm"
            onChange={(event) => setAuditEventFilter(event.target.value)}
            placeholder="event_type"
            value={auditEventFilter}
          />
          <select
            className="rounded border border-zinc-300 px-3 py-2 text-sm"
            onChange={(event) => setAuditOutcomeFilter(event.target.value)}
            value={auditOutcomeFilter}
          >
            <option value="">Any outcome</option>
            <option value="SUCCESS">SUCCESS</option>
            <option value="FAILURE">FAILURE</option>
            <option value="DENIED">DENIED</option>
          </select>
          <input
            className="rounded border border-zinc-300 px-3 py-2 text-sm"
            onChange={(event) => setAuditFromFilter(event.target.value)}
            type="datetime-local"
            value={auditFromFilter}
          />
          <input
            className="rounded border border-zinc-300 px-3 py-2 text-sm"
            onChange={(event) => setAuditToFilter(event.target.value)}
            type="datetime-local"
            value={auditToFilter}
          />
          <button
            className="rounded bg-zinc-950 px-4 py-2 text-sm font-medium text-white"
            onClick={applyAuditFilters}
            type="button"
          >
            Filter
          </button>
        </div>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[760px] border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-zinc-200 text-xs uppercase text-zinc-500">
                <th className="py-3 pr-4 font-medium">Event</th>
                <th className="py-3 pr-4 font-medium">Outcome</th>
                <th className="py-3 pr-4 font-medium">User</th>
                <th className="py-3 pr-4 font-medium">Target</th>
                <th className="py-3 pr-4 font-medium">Details</th>
                <th className="py-3 font-medium">Created</th>
              </tr>
            </thead>
            <tbody>
              {auditLogs?.items.length ? (
                auditLogs.items.map((log) => (
                  <tr key={log.id} className="border-b border-zinc-100 align-top">
                    <td className="py-3 pr-4 text-zinc-950">{log.event_type}</td>
                    <td className="py-3 pr-4">{pill(log.outcome, log.outcome)}</td>
                    <td className="py-3 pr-4 text-zinc-700">{log.user_id ?? "System"}</td>
                    <td className="py-3 pr-4 text-zinc-700">
                      {log.target_type ? `${log.target_type} ${log.target_id ?? ""}` : "None"}
                    </td>
                    <td className="max-w-xs py-3 pr-4 text-zinc-600">
                      {log.details_json ? JSON.stringify(log.details_json) : "None"}
                    </td>
                    <td className="py-3 text-zinc-700">{formatDateTime(log.created_at)}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td className="py-4 text-zinc-600" colSpan={6}>No audit logs found.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
