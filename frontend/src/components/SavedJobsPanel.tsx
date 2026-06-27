"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { apiFetch, formatDate, formatDateTime, type SavedJobListResponse } from "@/lib/api";

const pageSize = 10;

export function SavedJobsPanel() {
  const router = useRouter();
  const [savedJobs, setSavedJobs] = useState<SavedJobListResponse | null>(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [pendingJobId, setPendingJobId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    apiFetch<SavedJobListResponse>(`/saved-jobs?page=${page}&page_size=${pageSize}`)
      .then((response) => {
        if (active) {
          setSavedJobs(response);
        }
      })
      .catch((caught) => {
        const message = caught instanceof Error ? caught.message : "Unable to load saved jobs.";
        if (message === "Authentication required.") {
          router.push("/login");
          return;
        }
        if (active) {
          setError(message);
          setSavedJobs(null);
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

  async function onUnsave(jobId: number) {
    setPendingJobId(jobId);
    setError(null);
    try {
      await apiFetch<{ message: string }>(`/jobs/${jobId}/save`, { method: "DELETE" });
      setSavedJobs((current) =>
        current
          ? {
              ...current,
              total: Math.max(0, current.total - 1),
              items: current.items.filter((item) => item.job.id !== jobId)
            }
          : current
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to remove saved job.");
    } finally {
      setPendingJobId(null);
    }
  }

  const totalPages = savedJobs ? Math.max(1, Math.ceil(savedJobs.total / savedJobs.page_size)) : 1;

  return (
    <section>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-950">Saved Jobs</h1>
          <p className="mt-1 text-sm text-zinc-600">Only jobs saved by your account are shown.</p>
        </div>
        <Link className="rounded bg-zinc-950 px-4 py-2 text-sm font-medium text-white" href="/jobs">
          Browse jobs
        </Link>
      </div>

      {loading ? <p className="rounded border border-zinc-200 bg-white p-5 text-sm text-zinc-600">Loading saved jobs...</p> : null}
      {error ? <p className="rounded border border-red-200 bg-red-50 p-5 text-sm text-red-900">{error}</p> : null}
      {!loading && !error && savedJobs?.items.length === 0 ? (
        <p className="rounded border border-zinc-200 bg-white p-5 text-sm text-zinc-600">
          No saved jobs yet.
        </p>
      ) : null}

      <div className="space-y-4">
        {savedJobs?.items.map((item) => (
          <article key={item.job.id} className="rounded border border-zinc-200 bg-white p-5 shadow-sm">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <Link className="text-lg font-semibold text-zinc-950 hover:text-teal-800" href={`/jobs/${item.job.id}`}>
                  {item.job.title}
                </Link>
                <p className="mt-1 text-sm text-zinc-700">{item.job.company}</p>
              </div>
              <button
                className="rounded border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 disabled:cursor-not-allowed disabled:text-zinc-400"
                disabled={pendingJobId === item.job.id}
                onClick={() => onUnsave(item.job.id)}
                type="button"
              >
                {pendingJobId === item.job.id ? "Removing..." : "Remove"}
              </button>
            </div>
            <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-4">
              <div>
                <dt className="font-medium text-zinc-500">Location</dt>
                <dd className="mt-1 text-zinc-950">{item.job.location ?? "Not listed"}</dd>
              </div>
              <div>
                <dt className="font-medium text-zinc-500">Source</dt>
                <dd className="mt-1 text-zinc-950">{item.job.source.source_name}</dd>
              </div>
              <div>
                <dt className="font-medium text-zinc-500">Posted</dt>
                <dd className="mt-1 text-zinc-950">{formatDate(item.job.posting_date)}</dd>
              </div>
              <div>
                <dt className="font-medium text-zinc-500">Saved</dt>
                <dd className="mt-1 text-zinc-950">{formatDateTime(item.saved_at)}</dd>
              </div>
            </dl>
          </article>
        ))}
      </div>

      {savedJobs && savedJobs.total > savedJobs.page_size ? (
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
