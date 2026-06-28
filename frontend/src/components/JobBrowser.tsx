"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { apiFetch, formatDate, type JobListResponse, type JobSummary, type SavedJob } from "@/lib/api";

const pageSize = 10;

type Filters = {
  keyword: string;
  company: string;
  location: string;
  category: string;
  source: string;
};

const emptyFilters: Filters = {
  keyword: "",
  company: "",
  location: "",
  category: "",
  source: ""
};

function JobStatus({ job }: { job: JobSummary }) {
  if (!job.is_active) {
    return <span className="rounded border border-zinc-300 px-2 py-1 text-xs text-zinc-600">Inactive</span>;
  }
  if (job.is_suspicious) {
    return <span className="rounded border border-amber-300 bg-amber-50 px-2 py-1 text-xs text-amber-900">Review</span>;
  }
  return <span className="rounded border border-teal-200 bg-teal-50 px-2 py-1 text-xs text-teal-900">Active</span>;
}

type JobRowProps = {
  job: JobSummary;
  isSaving: boolean;
  isSaved: boolean;
  onSave: (jobId: number) => void;
};

function JobRow({ job, isSaving, isSaved, onSave }: JobRowProps) {
  return (
    <article className="rounded border border-zinc-200 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Link className="text-lg font-semibold text-zinc-950 hover:text-teal-800" href={`/jobs/${job.id}`}>
            {job.title}
          </Link>
          <p className="mt-1 text-sm text-zinc-700">{job.company}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <JobStatus job={job} />
          <button
            className="rounded bg-zinc-950 px-3 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-zinc-400"
            disabled={isSaving || isSaved}
            onClick={() => onSave(job.id)}
            type="button"
          >
            {isSaving ? "Saving..." : isSaved ? "Saved" : "Save"}
          </button>
        </div>
      </div>
      <dl className="mt-4 grid gap-3 text-sm text-zinc-600 sm:grid-cols-4">
        <div>
          <dt className="font-medium text-zinc-500">Location</dt>
          <dd className="mt-1 text-zinc-900">{job.location ?? "Not listed"}</dd>
        </div>
        <div>
          <dt className="font-medium text-zinc-500">Category</dt>
          <dd className="mt-1 text-zinc-900">{job.category ?? "Not listed"}</dd>
        </div>
        <div>
          <dt className="font-medium text-zinc-500">Source</dt>
          <dd className="mt-1 text-zinc-900">{job.source.source_name}</dd>
        </div>
        <div>
          <dt className="font-medium text-zinc-500">Posted</dt>
          <dd className="mt-1 text-zinc-900">{formatDate(job.posting_date)}</dd>
        </div>
      </dl>
    </article>
  );
}

export function JobBrowser() {
  const router = useRouter();
  const [filters, setFilters] = useState<Filters>(emptyFilters);
  const [appliedFilters, setAppliedFilters] = useState<Filters>(emptyFilters);
  const [page, setPage] = useState(1);
  const [jobs, setJobs] = useState<JobListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [pendingJobId, setPendingJobId] = useState<number | null>(null);
  const [savedJobIds, setSavedJobIds] = useState<Set<number>>(() => new Set());
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshIndex, setRefreshIndex] = useState(0);

  const query = useMemo(() => {
    const params = new URLSearchParams();
    Object.entries(appliedFilters).forEach(([key, value]) => {
      if (value.trim()) {
        params.set(key, value.trim());
      }
    });
    params.set("page", String(page));
    params.set("page_size", String(pageSize));
    return params.toString();
  }, [appliedFilters, page]);

  useEffect(() => {
    let active = true;
    apiFetch<JobListResponse>(`/jobs?${query}`)
      .then((response) => {
        if (active) {
          setJobs(response);
        }
      })
      .catch((caught) => {
        if (active) {
          setError(caught instanceof Error ? caught.message : "Unable to load jobs.");
          setJobs(null);
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
  }, [query, refreshIndex]);

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    setPage(1);
    setAppliedFilters(filters);
    setRefreshIndex((current) => current + 1);
  }

  function updateFilter(name: keyof Filters, value: string) {
    setFilters((current) => ({ ...current, [name]: value }));
  }

  async function onSave(jobId: number) {
    setPendingJobId(jobId);
    setSaveMessage(null);
    setError(null);
    try {
      await apiFetch<SavedJob>(`/jobs/${jobId}/save`, { method: "POST" });
      setSavedJobIds((current) => {
        const next = new Set(current);
        next.add(jobId);
        return next;
      });
      setSaveMessage("Job saved.");
    } catch (caught) {
      const nextMessage = caught instanceof Error ? caught.message : "Unable to save job.";
      if (nextMessage === "Authentication required.") {
        router.push("/login");
        return;
      }
      setError(nextMessage);
    } finally {
      setPendingJobId(null);
    }
  }

  const totalPages = jobs ? Math.max(1, Math.ceil(jobs.total / jobs.page_size)) : 1;

  return (
    <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
      <form className="h-fit rounded border border-zinc-200 bg-white p-5 shadow-sm" onSubmit={onSubmit}>
        <h1 className="text-xl font-semibold text-zinc-950">Jobs</h1>
        <div className="mt-5 space-y-4">
          <label className="block">
            <span className="text-sm font-medium text-zinc-800">Keyword</span>
            <input
              className="mt-2 w-full rounded border border-zinc-300 px-3 py-2 text-sm outline-none focus:border-teal-700 focus:ring-2 focus:ring-teal-100"
              maxLength={100}
              value={filters.keyword}
              onChange={(event) => updateFilter("keyword", event.target.value)}
            />
          </label>
          <label className="block">
            <span className="text-sm font-medium text-zinc-800">Company</span>
            <input
              className="mt-2 w-full rounded border border-zinc-300 px-3 py-2 text-sm outline-none focus:border-teal-700 focus:ring-2 focus:ring-teal-100"
              maxLength={100}
              value={filters.company}
              onChange={(event) => updateFilter("company", event.target.value)}
            />
          </label>
          <label className="block">
            <span className="text-sm font-medium text-zinc-800">Location</span>
            <input
              className="mt-2 w-full rounded border border-zinc-300 px-3 py-2 text-sm outline-none focus:border-teal-700 focus:ring-2 focus:ring-teal-100"
              maxLength={100}
              value={filters.location}
              onChange={(event) => updateFilter("location", event.target.value)}
            />
          </label>
          <label className="block">
            <span className="text-sm font-medium text-zinc-800">Category</span>
            <input
              className="mt-2 w-full rounded border border-zinc-300 px-3 py-2 text-sm outline-none focus:border-teal-700 focus:ring-2 focus:ring-teal-100"
              maxLength={100}
              value={filters.category}
              onChange={(event) => updateFilter("category", event.target.value)}
            />
          </label>
          <label className="block">
            <span className="text-sm font-medium text-zinc-800">Source</span>
            <select
              className="mt-2 w-full rounded border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:border-teal-700 focus:ring-2 focus:ring-teal-100"
              value={filters.source}
              onChange={(event) => updateFilter("source", event.target.value)}
            >
              <option value="">All approved sources</option>
              <option value="JobStreet">JobStreet</option>
              <option value="MyCareersFuture">MyCareersFuture</option>
            </select>
          </label>
          <button className="w-full rounded bg-zinc-950 px-4 py-2 text-sm font-medium text-white" type="submit">
            Search
          </button>
        </div>
      </form>

      <section>
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-zinc-600">
            {jobs ? `${jobs.total} active jobs` : "Loading active jobs"}
          </p>
          <Link className="rounded border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900" href="/saved-jobs">
            Saved jobs
          </Link>
        </div>
        {loading ? <p className="rounded border border-zinc-200 bg-white p-5 text-sm text-zinc-600">Loading jobs...</p> : null}
        {saveMessage ? (
          <p className="mb-4 rounded border border-teal-200 bg-teal-50 p-4 text-sm text-teal-900">{saveMessage}</p>
        ) : null}
        {error ? <p className="rounded border border-red-200 bg-red-50 p-5 text-sm text-red-900">{error}</p> : null}
        {!loading && !error && jobs?.items.length === 0 ? (
          <p className="rounded border border-zinc-200 bg-white p-5 text-sm text-zinc-600">
            No active jobs match these filters.
          </p>
        ) : null}
        <div className="space-y-4">
          {jobs?.items.map((job) => (
            <JobRow
              key={job.id}
              job={job}
              isSaved={savedJobIds.has(job.id)}
              isSaving={pendingJobId === job.id}
              onSave={onSave}
            />
          ))}
        </div>
        {jobs && jobs.total > jobs.page_size ? (
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
    </div>
  );
}
