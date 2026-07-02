"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { apiFetch, formatDate, formatDateTime, type CoverLetter, type RecommendationListResponse } from "@/lib/api";

const pageSize = 10;
const missingExtractionMessage = "No completed resume extraction is available.";

async function refreshRecommendations(): Promise<RecommendationListResponse> {
  return apiFetch<RecommendationListResponse>("/recommendations/refresh", {
    method: "POST"
  });
}

export function RecommendationsPanel() {
  const router = useRouter();
  const [recommendations, setRecommendations] = useState<RecommendationListResponse | null>(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [generatingJobId, setGeneratingJobId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    async function loadRecommendations() {
      setLoading(true);
      setError(null);
      try {
        const response = await apiFetch<RecommendationListResponse>(`/recommendations?page=${page}&page_size=${pageSize}`);
        if (!active) {
          return;
        }

        if (page === 1 && response.total === 0) {
          const refreshed = await refreshRecommendations();
          if (active) {
            setRecommendations(refreshed);
          }
          return;
        }

        setRecommendations(response);
      } catch (caught) {
        const message = caught instanceof Error ? caught.message : "Unable to load recommendations.";
        if (message === "Authentication required.") {
          router.push("/login");
          return;
        }
        if (active) {
          setError(message);
          setRecommendations(null);
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }
    loadRecommendations();
    return () => {
      active = false;
    };
  }, [page, router]);

  async function onRefresh() {
    setRefreshing(true);
    setError(null);
    try {
      const response = await refreshRecommendations();
      setPage(1);
      setRecommendations(response);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to refresh recommendations.");
    } finally {
      setRefreshing(false);
      setLoading(false);
    }
  }

  async function onGenerate(jobId: number) {
    setGeneratingJobId(jobId);
    setError(null);
    try {
      const draft = await apiFetch<CoverLetter>(`/jobs/${jobId}/cover-letter`, { method: "POST" });
      router.push(`/cover-letters/${draft.id}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to generate cover letter draft.");
    } finally {
      setGeneratingJobId(null);
    }
  }

  const totalPages = recommendations ? Math.max(1, Math.ceil(recommendations.total / recommendations.page_size)) : 1;
  const showMissingExtractionState = error === missingExtractionMessage;

  return (
    <section>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-950">Recommendations</h1>
          <p className="mt-1 text-sm text-zinc-600">Ranked from your completed extracted resume profile.</p>
        </div>
        <button
          className="rounded bg-zinc-950 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-zinc-400"
          disabled={refreshing}
          onClick={onRefresh}
          type="button"
        >
          {refreshing ? "Refreshing..." : "Refresh"}
        </button>
      </div>

      {loading ? <p className="rounded border border-zinc-200 bg-white p-5 text-sm text-zinc-600">Loading recommendations...</p> : null}
      {showMissingExtractionState ? (
        <div className="rounded border border-amber-200 bg-amber-50 p-5 text-sm text-amber-950">
          <p>{missingExtractionMessage}</p>
          <Link className="mt-3 inline-block font-medium text-teal-800" href="/resumes">
            Upload or review a resume
          </Link>
        </div>
      ) : null}
      {error && !showMissingExtractionState ? (
        <p className="rounded border border-red-200 bg-red-50 p-5 text-sm text-red-900">{error}</p>
      ) : null}
      {!loading && !error && recommendations?.items.length === 0 ? (
        <div className="rounded border border-zinc-200 bg-white p-5 text-sm text-zinc-600">
          <p>No matching jobs are available for your extracted resume profile yet.</p>
          <Link className="mt-3 inline-block font-medium text-teal-800" href="/jobs">
            Browse all jobs
          </Link>
        </div>
      ) : null}

      <div className="space-y-4">
        {recommendations?.items.map((item) => (
          <article key={item.id} className="rounded border border-zinc-200 bg-white p-5 shadow-sm">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-teal-700">
                  Rank {item.rank ?? "not set"} - {item.match_score.toFixed(1)}% match
                </p>
                <Link className="mt-2 block text-lg font-semibold text-zinc-950 hover:text-teal-800" href={`/jobs/${item.job.id}`}>
                  {item.job.title}
                </Link>
                <p className="mt-1 text-sm text-zinc-700">{item.job.company}</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  className="rounded bg-teal-700 px-3 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-zinc-400"
                  disabled={generatingJobId === item.job.id}
                  onClick={() => onGenerate(item.job.id)}
                  type="button"
                >
                  {generatingJobId === item.job.id ? "Generating..." : "Draft letter"}
                </button>
                <Link className="rounded border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900" href={`/jobs/${item.job.id}`}>
                  View job
                </Link>
              </div>
            </div>

            <p className="mt-4 text-sm leading-6 text-zinc-700">{item.rationale ?? "No rationale available."}</p>

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
                <dt className="font-medium text-zinc-500">Generated</dt>
                <dd className="mt-1 text-zinc-950">{formatDateTime(item.generated_at)}</dd>
              </div>
            </dl>
          </article>
        ))}
      </div>

      {recommendations && recommendations.total > recommendations.page_size ? (
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
