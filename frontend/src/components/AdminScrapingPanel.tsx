"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  apiFetch,
  formatDateTime,
  type AdminJobSource,
  type ScrapingRun,
  type User
} from "@/lib/api";
import { FormMessage } from "./FormControls";

type SourceActionState = Record<number, boolean>;

function statusClass(status: string): string {
  if (status === "SUCCESS") {
    return "border-teal-200 bg-teal-50 text-teal-800";
  }
  if (status === "FAILED") {
    return "border-red-200 bg-red-50 text-red-700";
  }
  return "border-zinc-200 bg-zinc-50 text-zinc-700";
}

export function AdminScrapingPanel() {
  const [user, setUser] = useState<User | null>(null);
  const [sources, setSources] = useState<AdminJobSource[]>([]);
  const [runs, setRuns] = useState<ScrapingRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [seeding, setSeeding] = useState(false);
  const [runningBySource, setRunningBySource] = useState<SourceActionState>({});
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const sourceNames = useMemo(() => {
    return new Map(sources.map((source) => [source.id, source.source_name]));
  }, [sources]);

  async function fetchAdminData() {
    const [currentUser, currentSources, currentRuns] = await Promise.all([
      apiFetch<User>("/me"),
      apiFetch<AdminJobSource[]>("/admin/job-sources"),
      apiFetch<ScrapingRun[]>("/admin/scraping-runs")
    ]);
    return { currentUser, currentSources, currentRuns };
  }

  async function refreshAdminData() {
    const { currentUser, currentSources, currentRuns } = await fetchAdminData();
    setUser(currentUser);
    setSources(currentSources);
    setRuns(currentRuns);
  }

  useEffect(() => {
    let active = true;
    Promise.all([
      apiFetch<User>("/me"),
      apiFetch<AdminJobSource[]>("/admin/job-sources"),
      apiFetch<ScrapingRun[]>("/admin/scraping-runs")
    ])
      .then(([currentUser, currentSources, currentRuns]) => {
        if (active) {
          setUser(currentUser);
          setSources(currentSources);
          setRuns(currentRuns);
        }
      })
      .catch((caught) => {
        if (active) {
          setError(caught instanceof Error ? caught.message : "Unable to load admin scraping data.");
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
      setError(caught instanceof Error ? caught.message : "Unable to seed job sources.");
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

  if (loading) {
    return <p className="text-sm text-zinc-600">Loading admin tools...</p>;
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
            <h1 className="text-2xl font-semibold text-zinc-950">Admin Scraping</h1>
            <p className="mt-1 text-sm text-zinc-600">Trigger approved job source scrapes and review run status.</p>
          </div>
          <Link className="rounded border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-900 hover:bg-zinc-100" href="/jobs">
            View jobs
          </Link>
        </div>
        <div className="mt-5 flex flex-wrap gap-3">
          <button
            className="rounded bg-zinc-950 px-4 py-2 text-sm font-medium text-white transition hover:bg-zinc-800 disabled:cursor-not-allowed disabled:bg-zinc-400"
            disabled={seeding}
            onClick={seedSources}
            type="button"
          >
            {seeding ? "Preparing..." : "Prepare approved sources"}
          </button>
        </div>
        <FormMessage message={message} tone="success" />
        <FormMessage message={error} tone="error" />
      </section>

      <section className="rounded border border-zinc-200 bg-white p-6 shadow-sm">
        <h2 className="text-lg font-semibold text-zinc-950">Job Sources</h2>
        <div className="mt-4 divide-y divide-zinc-200 rounded border border-zinc-200">
          {sources.length === 0 ? (
            <p className="p-4 text-sm text-zinc-600">No sources yet. Prepare approved sources first.</p>
          ) : (
            sources.map((source) => (
              <div key={source.id} className="flex flex-wrap items-center justify-between gap-4 p-4">
                <div>
                  <p className="font-medium text-zinc-950">{source.source_name}</p>
                  <p className="mt-1 break-all text-sm text-zinc-600">{source.base_url}</p>
                  <p className="mt-1 text-xs text-zinc-500">
                    {source.is_enabled ? "Enabled" : "Disabled"} · Added {formatDateTime(source.created_at)}
                  </p>
                </div>
                <button
                  className="rounded bg-teal-700 px-4 py-2 text-sm font-medium text-white transition hover:bg-teal-800 disabled:cursor-not-allowed disabled:bg-zinc-300"
                  disabled={!source.is_enabled || Boolean(runningBySource[source.id])}
                  onClick={() => runScrape(source)}
                  type="button"
                >
                  {runningBySource[source.id] ? "Running..." : "Run scrape"}
                </button>
              </div>
            ))
          )}
        </div>
      </section>

      <section className="rounded border border-zinc-200 bg-white p-6 shadow-sm">
        <h2 className="text-lg font-semibold text-zinc-950">Recent Runs</h2>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[680px] border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-zinc-200 text-xs uppercase text-zinc-500">
                <th className="py-3 pr-4 font-medium">Source</th>
                <th className="py-3 pr-4 font-medium">Status</th>
                <th className="py-3 pr-4 font-medium">Jobs</th>
                <th className="py-3 pr-4 font-medium">Started</th>
                <th className="py-3 pr-4 font-medium">Completed</th>
                <th className="py-3 font-medium">Error</th>
              </tr>
            </thead>
            <tbody>
              {runs.length === 0 ? (
                <tr>
                  <td className="py-4 text-zinc-600" colSpan={6}>
                    No scraping runs yet.
                  </td>
                </tr>
              ) : (
                runs.map((run) => (
                  <tr key={run.id} className="border-b border-zinc-100">
                    <td className="py-3 pr-4 text-zinc-950">{sourceNames.get(run.source_id) ?? `Source ${run.source_id}`}</td>
                    <td className="py-3 pr-4">
                      <span className={`rounded border px-2 py-1 text-xs font-medium ${statusClass(run.status)}`}>
                        {run.status}
                      </span>
                    </td>
                    <td className="py-3 pr-4 text-zinc-700">{run.jobs_retrieved}</td>
                    <td className="py-3 pr-4 text-zinc-700">{formatDateTime(run.started_at)}</td>
                    <td className="py-3 pr-4 text-zinc-700">{formatDateTime(run.completed_at)}</td>
                    <td className="py-3 text-zinc-600">{run.error_message ?? "None"}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
