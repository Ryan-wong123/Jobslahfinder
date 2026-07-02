"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { apiFetch, formatDateTime, type CoverLetter } from "@/lib/api";

const maxDraftLength = 20000;

export function CoverLetterEditor() {
  const params = useParams<{ coverLetterId: string }>();
  const router = useRouter();
  const [draft, setDraft] = useState<CoverLetter | null>(null);
  const [editedText, setEditedText] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    apiFetch<CoverLetter>(`/cover-letters/${params.coverLetterId}`)
      .then((response) => {
        if (active) {
          setDraft(response);
          setEditedText(response.edited_text ?? response.generated_text);
        }
      })
      .catch((caught) => {
        const nextMessage = caught instanceof Error ? caught.message : "Unable to load cover letter.";
        if (nextMessage === "Authentication required.") {
          router.push("/login");
          return;
        }
        if (active) {
          setError(nextMessage);
          setDraft(null);
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
  }, [params.coverLetterId, router]);

  async function onSave() {
    if (editedText.trim().length === 0 || editedText.length > maxDraftLength) {
      setError(`Draft text must be between 1 and ${maxDraftLength} characters.`);
      return;
    }
    setSaving(true);
    setMessage(null);
    setError(null);
    try {
      const response = await apiFetch<CoverLetter>(`/cover-letters/${params.coverLetterId}`, {
        method: "PATCH",
        body: JSON.stringify({ edited_text: editedText })
      });
      setDraft(response);
      setEditedText(response.edited_text ?? response.generated_text);
      setMessage("Draft saved.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to save draft.");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <p className="rounded border border-zinc-200 bg-white p-5 text-sm text-zinc-600">Loading draft...</p>;
  }

  if (error && !draft) {
    return (
      <section className="rounded border border-zinc-200 bg-white p-6 shadow-sm">
        <h1 className="text-xl font-semibold text-zinc-950">Draft unavailable</h1>
        <p className="mt-2 text-sm text-zinc-600">{error}</p>
        <Link className="mt-5 inline-flex rounded bg-zinc-950 px-4 py-2 text-sm font-medium text-white" href="/cover-letters">
          Back to cover letters
        </Link>
      </section>
    );
  }

  if (!draft) {
    return null;
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
      <section className="rounded border border-zinc-200 bg-white p-6 shadow-sm">
        <div className="mb-5">
          <p className="text-sm font-medium text-teal-800">Editable draft</p>
          <h1 className="mt-2 text-2xl font-semibold text-zinc-950">{draft.job.title}</h1>
          <p className="mt-1 text-sm text-zinc-700">{draft.job.company}</p>
        </div>
        <textarea
          className="min-h-[520px] w-full resize-y rounded border border-zinc-300 bg-white p-4 font-mono text-sm leading-6 text-zinc-950 outline-none focus:border-teal-700"
          maxLength={maxDraftLength}
          onChange={(event) => setEditedText(event.target.value)}
          value={editedText}
        />
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
          <p className="text-xs text-zinc-500">
            {editedText.length} / {maxDraftLength} characters
          </p>
          <button
            className="rounded bg-zinc-950 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-zinc-400"
            disabled={saving || editedText.trim().length === 0}
            onClick={onSave}
            type="button"
          >
            {saving ? "Saving..." : "Save draft"}
          </button>
        </div>
      </section>

      <aside className="h-fit rounded border border-zinc-200 bg-white p-5 shadow-sm">
        <h2 className="text-lg font-semibold text-zinc-950">Draft Status</h2>
        <dl className="mt-4 space-y-3 text-sm">
          <div>
            <dt className="font-medium text-zinc-500">Version</dt>
            <dd className="mt-1 text-zinc-950">{draft.version_no}</dd>
          </div>
          <div>
            <dt className="font-medium text-zinc-500">Created</dt>
            <dd className="mt-1 text-zinc-950">{formatDateTime(draft.created_at)}</dd>
          </div>
          <div>
            <dt className="font-medium text-zinc-500">Updated</dt>
            <dd className="mt-1 text-zinc-950">{formatDateTime(draft.updated_at)}</dd>
          </div>
        </dl>
        <p className="mt-4 rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-950">
          Review and tailor this draft before using it outside the platform.
        </p>
        {message ? <p className="mt-4 rounded border border-teal-200 bg-teal-50 p-3 text-sm text-teal-900">{message}</p> : null}
        {error ? <p className="mt-4 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-900">{error}</p> : null}
        <div className="mt-4 flex flex-col gap-2">
          <Link className="rounded border border-zinc-300 bg-white px-3 py-2 text-center text-sm text-zinc-900" href={`/jobs/${draft.job.id}`}>
            View job
          </Link>
          <Link className="rounded border border-zinc-300 bg-white px-3 py-2 text-center text-sm text-zinc-900" href="/cover-letters">
            All drafts
          </Link>
        </div>
      </aside>
    </div>
  );
}
