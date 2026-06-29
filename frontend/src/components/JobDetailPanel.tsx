"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { apiFetch, formatDate, type CoverLetter, type JobDetail, type SavedJob } from "@/lib/api";

export function JobDetailPanel() {
  const params = useParams<{ jobId: string }>();
  const router = useRouter();
  const [job, setJob] = useState<JobDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [warningVisible, setWarningVisible] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    apiFetch<JobDetail>(`/jobs/${params.jobId}`)
      .then((response) => {
        if (active) {
          setJob(response);
        }
      })
      .catch((caught) => {
        if (active) {
          setError(caught instanceof Error ? caught.message : "Unable to load job.");
          setJob(null);
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
  }, [params.jobId]);

  async function onSave() {
    setSaving(true);
    setMessage(null);
    setError(null);
    try {
      await apiFetch<SavedJob>(`/jobs/${params.jobId}/save`, { method: "POST" });
      setMessage("Job saved.");
    } catch (caught) {
      const nextMessage = caught instanceof Error ? caught.message : "Unable to save job.";
      if (nextMessage === "Authentication required.") {
        router.push("/login");
        return;
      }
      setError(nextMessage);
    } finally {
      setSaving(false);
    }
  }

  async function onGenerateCoverLetter() {
    setGenerating(true);
    setMessage(null);
    setError(null);
    try {
      const draft = await apiFetch<CoverLetter>(`/jobs/${params.jobId}/cover-letter`, { method: "POST" });
      router.push(`/cover-letters/${draft.id}`);
    } catch (caught) {
      const nextMessage = caught instanceof Error ? caught.message : "Unable to generate draft.";
      if (nextMessage === "Authentication required.") {
        router.push("/login");
        return;
      }
      setError(nextMessage);
    } finally {
      setGenerating(false);
    }
  }

  function openExternalSource() {
    if (!job) {
      return;
    }
    window.open(job.job_url, "_blank", "noopener,noreferrer");
    setWarningVisible(false);
  }

  if (loading) {
    return <p className="rounded border border-zinc-200 bg-white p-5 text-sm text-zinc-600">Loading job...</p>;
  }

  if (error || !job) {
    return (
      <section className="rounded border border-zinc-200 bg-white p-6 shadow-sm">
        <h1 className="text-xl font-semibold text-zinc-950">Job unavailable</h1>
        <p className="mt-2 text-sm text-zinc-600">{error ?? "Resource not found."}</p>
        <Link className="mt-5 inline-flex rounded bg-zinc-950 px-4 py-2 text-sm font-medium text-white" href="/jobs">
          Back to jobs
        </Link>
      </section>
    );
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
      <article className="rounded border border-zinc-200 bg-white p-6 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-sm font-medium text-teal-800">{job.source.source_name}</p>
            <h1 className="mt-2 text-3xl font-semibold leading-tight text-zinc-950">{job.title}</h1>
            <p className="mt-2 text-base text-zinc-700">{job.company}</p>
          </div>
          <span className="rounded border border-teal-200 bg-teal-50 px-3 py-1 text-xs font-medium text-teal-900">
            Active
          </span>
        </div>
        <dl className="mt-6 grid gap-4 border-y border-zinc-200 py-5 text-sm sm:grid-cols-3">
          <div>
            <dt className="font-medium text-zinc-500">Location</dt>
            <dd className="mt-1 text-zinc-950">{job.location ?? "Not listed"}</dd>
          </div>
          <div>
            <dt className="font-medium text-zinc-500">Category</dt>
            <dd className="mt-1 text-zinc-950">{job.category ?? "Not listed"}</dd>
          </div>
          <div>
            <dt className="font-medium text-zinc-500">Posted</dt>
            <dd className="mt-1 text-zinc-950">{formatDate(job.posting_date)}</dd>
          </div>
        </dl>
        <section className="mt-6">
          <h2 className="text-lg font-semibold text-zinc-950">Description</h2>
          <p className="mt-3 whitespace-pre-line text-sm leading-7 text-zinc-700">
            {job.description ?? "No description was provided by the source."}
          </p>
        </section>
      </article>

      <aside className="h-fit rounded border border-zinc-200 bg-white p-5 shadow-sm">
        <h2 className="text-lg font-semibold text-zinc-950">Actions</h2>
        <div className="mt-4 space-y-3">
          {message ? <p className="rounded border border-teal-200 bg-teal-50 px-3 py-2 text-sm text-teal-900">{message}</p> : null}
          {error ? <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900">{error}</p> : null}
          <button
            className="w-full rounded bg-zinc-950 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-zinc-400"
            disabled={saving}
            onClick={onSave}
            type="button"
          >
            {saving ? "Saving..." : "Save job"}
          </button>
          <button
            className="w-full rounded border border-teal-700 bg-teal-700 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:border-zinc-300 disabled:bg-zinc-400"
            disabled={generating}
            onClick={onGenerateCoverLetter}
            type="button"
          >
            {generating ? "Generating..." : "Generate cover letter draft"}
          </button>
          <button
            className="w-full rounded border border-zinc-300 bg-white px-4 py-2 text-sm font-medium text-zinc-900"
            onClick={() => setWarningVisible(true)}
            type="button"
          >
            Open original source
          </button>
        </div>
        {warningVisible ? (
          <div className="mt-4 rounded border border-amber-200 bg-amber-50 p-4">
            <p className="text-sm text-amber-950">{job.external_link_warning}</p>
            <div className="mt-3 flex gap-2">
              <button
                className="rounded bg-zinc-950 px-3 py-2 text-sm font-medium text-white"
                onClick={openExternalSource}
                type="button"
              >
                Continue
              </button>
              <button
                className="rounded border border-amber-300 bg-white px-3 py-2 text-sm font-medium text-amber-950"
                onClick={() => setWarningVisible(false)}
                type="button"
              >
                Cancel
              </button>
            </div>
          </div>
        ) : null}
      </aside>
    </div>
  );
}
