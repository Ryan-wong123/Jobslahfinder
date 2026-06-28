"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  apiFetch,
  formatBytes,
  formatDateTime,
  type Resume,
  type ResumeExtraction
} from "@/lib/api";
import { FormMessage } from "./FormControls";

function statusClass(status: string): string {
  if (status === "COMPLETED" || status === "STORED") {
    return "border-teal-200 bg-teal-50 text-teal-900";
  }
  if (status === "FAILED" || status === "REJECTED") {
    return "border-red-200 bg-red-50 text-red-900";
  }
  return "border-amber-200 bg-amber-50 text-amber-900";
}

function StatusBadge({ status }: { status: string }) {
  return <span className={`rounded border px-2 py-1 text-xs font-medium ${statusClass(status)}`}>{status}</span>;
}

export function ResumeDetailPanel({ resumeId }: { resumeId: number }) {
  const router = useRouter();
  const [resume, setResume] = useState<Resume | null>(null);
  const [extraction, setExtraction] = useState<ResumeExtraction | null>(null);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    Promise.all([
      apiFetch<Resume>(`/resumes/${resumeId}`),
      apiFetch<ResumeExtraction>(`/resumes/${resumeId}/extraction`)
    ])
      .then(([resumeResponse, extractionResponse]) => {
        if (active) {
          setResume(resumeResponse);
          setExtraction(extractionResponse);
          setError(null);
        }
      })
      .catch((caught) => {
        const nextMessage = caught instanceof Error ? caught.message : "Unable to load resume.";
        if (nextMessage === "Authentication required.") {
          router.push("/login");
          return;
        }
        if (active) {
          setError(nextMessage);
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
  }, [resumeId, router]);

  async function onDelete() {
    setDeleting(true);
    setError(null);
    setMessage(null);
    try {
      await apiFetch<{ message: string }>(`/resumes/${resumeId}`, { method: "DELETE" });
      setMessage("Resume deleted.");
      router.push("/resumes");
      router.refresh();
    } catch (caught) {
      const nextMessage = caught instanceof Error ? caught.message : "Unable to delete resume.";
      if (nextMessage === "Authentication required.") {
        router.push("/login");
        return;
      }
      setError(nextMessage);
      setDeleting(false);
    }
  }

  if (loading) {
    return <p className="rounded border border-zinc-200 bg-white p-5 text-sm text-zinc-600">Loading resume...</p>;
  }

  if (error && !resume) {
    return (
      <div className="rounded border border-red-200 bg-red-50 p-5 text-sm text-red-900">
        <p>{error}</p>
        <Link className="mt-3 inline-block font-medium text-red-950 underline" href="/resumes">
          Back to resumes
        </Link>
      </div>
    );
  }

  if (!resume || !extraction) {
    return null;
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
      <section className="rounded border border-zinc-200 bg-white p-6 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold text-zinc-950">{resume.original_filename}</h1>
            <p className="mt-1 text-sm text-zinc-600">{resume.mime_type}</p>
          </div>
          <StatusBadge status={resume.upload_status} />
        </div>
        <dl className="mt-6 grid gap-4 sm:grid-cols-2">
          <div className="border-t border-zinc-200 pt-4">
            <dt className="text-xs font-medium uppercase text-zinc-500">Uploaded</dt>
            <dd className="mt-1 text-sm text-zinc-950">{formatDateTime(resume.uploaded_at)}</dd>
          </div>
          <div className="border-t border-zinc-200 pt-4">
            <dt className="text-xs font-medium uppercase text-zinc-500">Size</dt>
            <dd className="mt-1 text-sm text-zinc-950">{formatBytes(resume.file_size_bytes)}</dd>
          </div>
          <div className="border-t border-zinc-200 pt-4 sm:col-span-2">
            <dt className="text-xs font-medium uppercase text-zinc-500">File hash</dt>
            <dd className="mt-1 break-all font-mono text-xs text-zinc-700">{resume.file_hash}</dd>
          </div>
        </dl>
      </section>

      <section className="rounded border border-zinc-200 bg-white p-6 shadow-sm">
        <div className="flex items-start justify-between gap-3">
          <h2 className="text-lg font-semibold text-zinc-950">Extraction</h2>
          <StatusBadge status={extraction.processing_status} />
        </div>
        <dl className="mt-5 space-y-4 text-sm">
          <div className="border-t border-zinc-200 pt-4">
            <dt className="font-medium text-zinc-500">Processed</dt>
            <dd className="mt-1 text-zinc-950">{formatDateTime(extraction.processed_at)}</dd>
          </div>
          <div className="border-t border-zinc-200 pt-4">
            <dt className="font-medium text-zinc-500">Years experience</dt>
            <dd className="mt-1 text-zinc-950">{extraction.years_experience ?? "Not extracted yet"}</dd>
          </div>
        </dl>
        <FormMessage message={message} tone="success" />
        <FormMessage message={error} tone="error" />
        <div className="mt-6 flex flex-wrap gap-3">
          <Link className="rounded border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900" href="/resumes">
            Back
          </Link>
          <Link
            className="rounded bg-zinc-950 px-3 py-2 text-sm font-medium text-white"
            href={`/resumes/${resumeId}/profile`}
          >
            Review profile
          </Link>
          <button
            className="rounded border border-red-300 bg-white px-3 py-2 text-sm font-medium text-red-800 transition hover:bg-red-50 disabled:cursor-not-allowed disabled:text-red-300"
            disabled={deleting}
            onClick={onDelete}
            type="button"
          >
            {deleting ? "Deleting..." : "Delete"}
          </button>
        </div>
      </section>
    </div>
  );
}
