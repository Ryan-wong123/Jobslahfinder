"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { apiFetch, formatDateTime, type CoverLetterListResponse } from "@/lib/api";

const pageSize = 10;

export function CoverLettersPanel() {
  const router = useRouter();
  const [drafts, setDrafts] = useState<CoverLetterListResponse | null>(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    apiFetch<CoverLetterListResponse>(`/cover-letters?page=${page}&page_size=${pageSize}`)
      .then((response) => {
        if (active) {
          setDrafts(response);
        }
      })
      .catch((caught) => {
        const message = caught instanceof Error ? caught.message : "Unable to load cover letters.";
        if (message === "Authentication required.") {
          router.push("/login");
          return;
        }
        if (active) {
          setError(message);
          setDrafts(null);
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

  const totalPages = drafts ? Math.max(1, Math.ceil(drafts.total / drafts.page_size)) : 1;

  return (
    <section>
      <div className="mb-6">
        <h1 className="text-2xl font-semibold text-zinc-950">Cover Letters</h1>
        <p className="mt-1 text-sm text-zinc-600">Generated text is an editable draft for your review.</p>
      </div>

      {loading ? <p className="rounded border border-zinc-200 bg-white p-5 text-sm text-zinc-600">Loading drafts...</p> : null}
      {error ? <p className="rounded border border-red-200 bg-red-50 p-5 text-sm text-red-900">{error}</p> : null}
      {!loading && !error && drafts?.items.length === 0 ? (
        <div className="rounded border border-zinc-200 bg-white p-5 text-sm text-zinc-600">
          <p>No cover letter drafts yet.</p>
          <Link className="mt-3 inline-block font-medium text-teal-800" href="/jobs">
            Browse jobs
          </Link>
        </div>
      ) : null}

      <div className="space-y-4">
        {drafts?.items.map((draft) => (
          <article key={draft.id} className="rounded border border-zinc-200 bg-white p-5 shadow-sm">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-teal-700">
                  Version {draft.version_no} - Updated {formatDateTime(draft.updated_at)}
                </p>
                <Link className="mt-2 block text-lg font-semibold text-zinc-950 hover:text-teal-800" href={`/cover-letters/${draft.id}`}>
                  {draft.job.title}
                </Link>
                <p className="mt-1 text-sm text-zinc-700">{draft.job.company}</p>
              </div>
              <Link className="rounded bg-zinc-950 px-3 py-2 text-sm font-medium text-white" href={`/cover-letters/${draft.id}`}>
                Edit draft
              </Link>
            </div>
            <p className="mt-4 max-h-20 overflow-hidden whitespace-pre-line text-sm leading-6 text-zinc-700">
              {draft.edited_text ?? draft.generated_text}
            </p>
          </article>
        ))}
      </div>

      {drafts && drafts.total > drafts.page_size ? (
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
