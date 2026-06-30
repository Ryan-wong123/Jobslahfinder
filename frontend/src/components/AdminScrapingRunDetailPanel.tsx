"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { apiFetch, formatDateTime, type ScrapingRun } from "@/lib/api";

export function AdminScrapingRunDetailPanel() {
  const params = useParams<{ runId: string }>();
  const [run, setRun] = useState<ScrapingRun | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    apiFetch<ScrapingRun>(`/admin/scraping-runs/${params.runId}`)
      .then((response) => {
        if (active) {
          setRun(response);
        }
      })
      .catch((caught) => {
        if (active) {
          setError(caught instanceof Error ? caught.message : "Unable to load scraping run details.");
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
  }, [params.runId]);

  if (loading) {
    return <p className="text-sm text-zinc-600">Loading scraping run...</p>;
  }

  if (error || !run) {
    return (
      <section className="rounded border border-zinc-200 bg-white p-6 shadow-sm">
        <h1 className="text-2xl font-semibold text-zinc-950">Scraping Run</h1>
        <p className="mt-2 text-sm text-red-700">{error ?? "Unable to load scraping run."}</p>
        <Link className="mt-5 inline-block rounded bg-zinc-950 px-4 py-2 text-sm font-medium text-white" href="/admin">
          Back to admin
        </Link>
      </section>
    );
  }

  return (
    <section className="rounded border border-zinc-200 bg-white p-6 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-950">Scraping Run {run.id}</h1>
          <p className="mt-1 text-sm text-zinc-600">Source {run.source_id}</p>
        </div>
        <Link className="rounded border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-900" href="/admin">
          Back
        </Link>
      </div>
      <dl className="mt-6 grid gap-4 md:grid-cols-3">
        <div className="rounded border border-zinc-200 p-4">
          <dt className="text-xs uppercase text-zinc-500">Status</dt>
          <dd className="mt-2 text-zinc-950">{run.status}</dd>
        </div>
        <div className="rounded border border-zinc-200 p-4">
          <dt className="text-xs uppercase text-zinc-500">Jobs retrieved</dt>
          <dd className="mt-2 text-zinc-950">{run.jobs_retrieved}</dd>
        </div>
        <div className="rounded border border-zinc-200 p-4">
          <dt className="text-xs uppercase text-zinc-500">Completed</dt>
          <dd className="mt-2 text-zinc-950">{formatDateTime(run.completed_at)}</dd>
        </div>
        <div className="rounded border border-zinc-200 p-4">
          <dt className="text-xs uppercase text-zinc-500">Started</dt>
          <dd className="mt-2 text-zinc-950">{formatDateTime(run.started_at)}</dd>
        </div>
        <div className="rounded border border-zinc-200 p-4 md:col-span-2">
          <dt className="text-xs uppercase text-zinc-500">Safe error</dt>
          <dd className="mt-2 text-zinc-950">{run.error_message ?? "None"}</dd>
        </div>
      </dl>
    </section>
  );
}
