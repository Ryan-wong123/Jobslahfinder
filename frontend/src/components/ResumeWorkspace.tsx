"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  apiFetch,
  formatBytes,
  formatDateTime,
  type Resume,
  type ResumeListResponse
} from "@/lib/api";
import { FormMessage } from "./FormControls";

function StatusBadge({ status }: { status: string }) {
  const classes =
    status === "STORED"
      ? "border-teal-200 bg-teal-50 text-teal-900"
      : status === "DELETED" || status === "REJECTED"
        ? "border-red-200 bg-red-50 text-red-900"
        : "border-amber-200 bg-amber-50 text-amber-900";
  return <span className={`rounded border px-2 py-1 text-xs font-medium ${classes}`}>{status}</span>;
}

function ResumeRow({ resume }: { resume: Resume }) {
  return (
    <article className="rounded border border-zinc-200 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Link className="text-lg font-semibold text-zinc-950 hover:text-teal-800" href={`/resumes/${resume.id}`}>
            {resume.original_filename}
          </Link>
          <p className="mt-1 text-sm text-zinc-600">{resume.mime_type}</p>
        </div>
        <StatusBadge status={resume.upload_status} />
      </div>
      <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-3">
        <div>
          <dt className="font-medium text-zinc-500">Size</dt>
          <dd className="mt-1 text-zinc-900">{formatBytes(resume.file_size_bytes)}</dd>
        </div>
        <div>
          <dt className="font-medium text-zinc-500">Uploaded</dt>
          <dd className="mt-1 text-zinc-900">{formatDateTime(resume.uploaded_at)}</dd>
        </div>
        <div>
          <dt className="font-medium text-zinc-500">File hash</dt>
          <dd className="mt-1 break-all font-mono text-xs text-zinc-700">{resume.file_hash.slice(0, 24)}...</dd>
        </div>
      </dl>
    </article>
  );
}

export function ResumeWorkspace() {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [resumes, setResumes] = useState<ResumeListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [refreshIndex, setRefreshIndex] = useState(0);

  useEffect(() => {
    let active = true;
    apiFetch<ResumeListResponse>("/resumes")
      .then((response) => {
        if (active) {
          setResumes(response);
          setError(null);
        }
      })
      .catch((caught) => {
        const nextMessage = caught instanceof Error ? caught.message : "Unable to load resumes.";
        if (nextMessage === "Authentication required.") {
          router.push("/login");
          return;
        }
        if (active) {
          setResumes(null);
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
  }, [refreshIndex, router]);

  async function onUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setUploading(true);
    setError(null);
    setMessage(null);

    const selectedFile = fileInputRef.current?.files?.[0];
    if (!selectedFile) {
      setError("Choose a PDF or DOCX resume to upload.");
      setUploading(false);
      return;
    }

    const formData = new FormData();
    formData.set("file", selectedFile);
    try {
      await apiFetch<Resume>("/resumes", {
        method: "POST",
        body: formData
      });
      setMessage("Resume uploaded. Extraction is queued for processing.");
      event.currentTarget.reset();
      setLoading(true);
      setRefreshIndex((current) => current + 1);
    } catch (caught) {
      const nextMessage = caught instanceof Error ? caught.message : "Unable to upload resume.";
      if (nextMessage === "Authentication required.") {
        router.push("/login");
        return;
      }
      setError(nextMessage);
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[340px_1fr]">
      <section className="h-fit rounded border border-zinc-200 bg-white p-5 shadow-sm">
        <h1 className="text-xl font-semibold text-zinc-950">Resumes</h1>
        <form className="mt-5 space-y-4" onSubmit={onUpload}>
          <FormMessage message={message} tone="success" />
          <FormMessage message={error} tone="error" />
          <label className="block">
            <span className="text-sm font-medium text-zinc-800">Resume file</span>
            <input
              ref={fileInputRef}
              className="mt-2 w-full rounded border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-950 outline-none transition file:mr-3 file:rounded file:border-0 file:bg-zinc-950 file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-white focus:border-teal-700 focus:ring-2 focus:ring-teal-100"
              name="file"
              type="file"
              accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
              required
            />
          </label>
          <button
            className="w-full rounded bg-zinc-950 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-zinc-800 disabled:cursor-not-allowed disabled:bg-zinc-400"
            disabled={uploading}
            type="submit"
          >
            {uploading ? "Uploading..." : "Upload resume"}
          </button>
        </form>
      </section>

      <section>
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-zinc-600">{resumes ? `${resumes.total} resumes` : "Loading resumes"}</p>
          <Link className="rounded border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900" href="/jobs">
            Browse jobs
          </Link>
        </div>
        {loading ? (
          <p className="rounded border border-zinc-200 bg-white p-5 text-sm text-zinc-600">Loading resumes...</p>
        ) : null}
        {!loading && !error && resumes?.items.length === 0 ? (
          <p className="rounded border border-zinc-200 bg-white p-5 text-sm text-zinc-600">
            No resumes uploaded yet.
          </p>
        ) : null}
        <div className="space-y-4">{resumes?.items.map((resume) => <ResumeRow key={resume.id} resume={resume} />)}</div>
      </section>
    </div>
  );
}
