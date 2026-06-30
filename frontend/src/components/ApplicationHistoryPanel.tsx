"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { apiFetch, formatDateTime, type ApplicationHistoryListResponse } from "@/lib/api";

const pageSize = 10;

const actionLabels: Record<string, string> = {
  cover_letter_generated: "Cover letter generated",
  cover_letter_edited: "Cover letter edited",
  job_saved: "Job saved",
  job_unsaved: "Job removed",
  recommendations_refreshed: "Recommendations refreshed"
};

function actionLabel(actionType: string): string {
  return actionLabels[actionType] ?? "Activity recorded";
}

export function ApplicationHistoryPanel() {
  const router = useRouter();
  const [history, setHistory] = useState<ApplicationHistoryListResponse | null>(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    apiFetch<ApplicationHistoryListResponse>(`/application-history?page=${page}&page_size=${pageSize}`)
      .then((response) => {
        if (active) {
          setHistory(response);
        }
      })
      .catch((caught) => {
        const message = caught instanceof Error ? caught.message : "Unable to load application history.";
        if (message === "Authentication required.") {
          router.push("/login");
          return;
        }
        if (active) {
          setError("Unable to load application history.");
          setHistory(null);
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
  }, [page, router]);

  const totalPages = history ? Math.max(1, Math.ceil(history.total / history.page_size)) : 1;

  return (
    <section>
      <div className="mb-6">
        <h1 className="text-2xl font-semibold text-zinc-950">Application History</h1>
        <p className="mt-1 text-sm text-zinc-600">Review your saved jobs, recommendation refreshes, and draft activity.</p>
      </div>

      {loading ? <p className="rounded border border-zinc-200 bg-white p-5 text-sm text-zinc-600">Loading history...</p> : null}
      {error ? <p className="rounded border border-red-200 bg-red-50 p-5 text-sm text-red-900">{error}</p> : null}
      {!loading && !error && history?.items.length === 0 ? (
        <div className="rounded border border-zinc-200 bg-white p-5 text-sm text-zinc-600">
          <p>No application history yet.</p>
          <Link className="mt-3 inline-block font-medium text-teal-800" href="/jobs">
            Browse jobs
          </Link>
        </div>
      ) : null}

      <div className="space-y-3">
        {history?.items.map((item) => (
          <article key={item.id} className="rounded border border-zinc-200 bg-white p-5 shadow-sm">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <p className="text-xs font-semibold uppercase text-teal-700">{actionLabel(item.action_type)}</p>
                <h2 className="mt-2 text-lg font-semibold text-zinc-950">
                  {item.job ? item.job.title : "Platform activity"}
                </h2>
                <p className="mt-1 text-sm text-zinc-700">
                  {item.job ? item.job.company : "No job attached"}
                </p>
                <p className="mt-2 text-sm text-zinc-500">{formatDateTime(item.action_time)}</p>
              </div>
              <div className="flex flex-wrap gap-2">
                {item.job ? (
                  <Link className="rounded border border-zinc-300 bg-white px-3 py-2 text-sm font-medium text-zinc-900" href={`/jobs/${item.job.id}`}>
                    View job
                  </Link>
                ) : null}
                {item.cover_letter_id ? (
                  <Link className="rounded bg-zinc-950 px-3 py-2 text-sm font-medium text-white" href={`/cover-letters/${item.cover_letter_id}`}>
                    Open draft
                  </Link>
                ) : null}
              </div>
            </div>
          </article>
        ))}
      </div>

      {history && history.total > history.page_size ? (
        <div className="mt-5 flex items-center justify-between gap-3">
          <button
            className="rounded border border-zinc-300 bg-white px-3 py-2 text-sm disabled:cursor-not-allowed disabled:text-zinc-400"
            disabled={page <= 1}
            onClick={() => {
              setLoading(true);
              setError(null);
              setPage((current) => Math.max(1, current - 1));
            }}
            type="button"
          >
            Previous
          </button>
          <p className="text-sm text-zinc-600">
            Page {page} of {totalPages}
          </p>
          <button
            className="rounded border border-zinc-300 bg-white px-3 py-2 text-sm disabled:cursor-not-allowed disabled:text-zinc-400"
            disabled={page >= totalPages}
            onClick={() => {
              setLoading(true);
              setError(null);
              setPage((current) => Math.min(totalPages, current + 1));
            }}
            type="button"
          >
            Next
          </button>
        </div>
      ) : null}
    </section>
  );
}
