"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import {
  apiFetch,
  formatDateTime,
  type Resume,
  type ResumeExtraction,
  type ResumeExtractionUpdate
} from "@/lib/api";
import { FormMessage } from "./FormControls";

function toLineText(items: Array<Record<string, unknown>>): string {
  return items
    .map((item) => {
      const value = item.description ?? item.title ?? item.institution ?? item.credential;
      return typeof value === "string" ? value : "";
    })
    .filter(Boolean)
    .join("\n");
}

function toDescriptionItems(value: string): Array<{ description: string }> {
  return value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .slice(0, 50)
    .map((description) => ({ description }));
}

function ItemList({ items, empty }: { items: string[]; empty: string }) {
  if (items.length === 0) {
    return <p className="text-sm text-zinc-600">{empty}</p>;
  }
  return (
    <ul className="mt-3 flex flex-wrap gap-2">
      {items.map((item) => (
        <li key={item} className="rounded border border-zinc-200 bg-zinc-50 px-2.5 py-1 text-sm text-zinc-800">
          {item}
        </li>
      ))}
    </ul>
  );
}

function formatYearsToDuration(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "Not provided";
  }

  if (typeof value !== "number" && typeof value !== "string") {
    return "Not provided";
  }

  const yearsValue = Number(value);

  if (Number.isNaN(yearsValue) || yearsValue <= 0) {
    return "Not provided";
  }

  const totalMonths = Math.round(yearsValue * 12);
  const wholeYears = Math.floor(totalMonths / 12);
  const months = totalMonths % 12;

  if (wholeYears === 0 && months === 0) {
    return "Less than 1 month";
  }

  if (wholeYears === 0) {
    return `${months} ${months === 1 ? "month" : "months"}`;
  }

  if (months === 0) {
    return `${wholeYears} ${wholeYears === 1 ? "year" : "years"}`;
  }

  return `${wholeYears} ${wholeYears === 1 ? "year" : "years"}, ${months} ${
    months === 1 ? "month" : "months"
  }`;
}

function calculateTotalExperienceDuration(experience: Array<Record<string, unknown>>): string {
  const totalYears = experience.reduce((sum, item) => {
    const years = item.years;

    if (typeof years === "number") {
      return sum + years;
    }

    if (typeof years === "string") {
      const parsed = Number(years);
      return Number.isNaN(parsed) ? sum : sum + parsed;
    }

    return sum;
  }, 0);

  return formatYearsToDuration(totalYears);
}

export function ExtractedProfilePanel({ resumeId, editing }: { resumeId: number; editing: boolean }) {
  const router = useRouter();
  const [resume, setResume] = useState<Resume | null>(null);
  const [extraction, setExtraction] = useState<ResumeExtraction | null>(null);
  const [skills, setSkills] = useState("");
  const [experience, setExperience] = useState("");
  const [education, setEducation] = useState("");
  const [yearsExperience, setYearsExperience] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    Promise.all([
      apiFetch<Resume>(`/resumes/${resumeId}`),
      apiFetch<ResumeExtraction>(`/resumes/${resumeId}/extraction`)
    ])
      .then(([resumeResponse, extractionResponse]) => {
        if (!active) {
          return;
        }
        setResume(resumeResponse);
        setExtraction(extractionResponse);
        setSkills(extractionResponse.skills.join(", "));
        setExperience(toLineText(extractionResponse.experience));
        setEducation(toLineText(extractionResponse.education));
        setYearsExperience(
          extractionResponse.years_experience === null ? "" : String(extractionResponse.years_experience)
        );
        setError(null);
      })
      .catch((caught) => {
        const nextMessage = caught instanceof Error ? caught.message : "Unable to load extracted profile.";
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

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setMessage(null);
    const parsedYears = yearsExperience.trim() ? Number(yearsExperience) : null;
    const payload: ResumeExtractionUpdate = {
      skills: skills
        .split(",")
        .map((skill) => skill.trim())
        .filter(Boolean),
      experience: toDescriptionItems(experience),
      education: toDescriptionItems(education),
      years_experience: Number.isFinite(parsedYears) ? parsedYears : null
    };
    try {
      const updated = await apiFetch<ResumeExtraction>(`/resumes/${resumeId}/extraction`, {
        method: "PATCH",
        body: JSON.stringify(payload)
      });
      setExtraction(updated);
      setMessage("Extracted profile saved.");
      router.push(`/resumes/${resumeId}/profile`);
      router.refresh();
    } catch (caught) {
      const nextMessage = caught instanceof Error ? caught.message : "Unable to update extracted profile.";
      if (nextMessage === "Authentication required.") {
        router.push("/login");
        return;
      }
      setError(nextMessage);
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <p className="rounded border border-zinc-200 bg-white p-5 text-sm text-zinc-600">Loading profile...</p>;
  }

  if (error && !extraction) {
    return <p className="rounded border border-red-200 bg-red-50 p-5 text-sm text-red-900">{error}</p>;
  }

  if (!resume || !extraction) {
    return (
      <p className="rounded border border-zinc-200 bg-white p-5 text-sm text-zinc-600">
        No extracted profile is available for this resume.
      </p>
    );
  }

  if (editing) {
    return (
      <form className="mx-auto max-w-3xl rounded border border-zinc-200 bg-white p-6 shadow-sm" method="post" onSubmit={onSubmit}>
        <div className="mb-6">
          <p className="text-sm text-zinc-600">{resume.original_filename}</p>
          <h1 className="mt-1 text-2xl font-semibold text-zinc-950">Edit Extracted Profile</h1>
        </div>
        <div className="space-y-5">
          <FormMessage message={message} tone="success" />
          <FormMessage message={error} tone="error" />
          <label className="block">
            <span className="text-sm font-medium text-zinc-800">Skills</span>
            <input
              className="mt-2 w-full rounded border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-950 outline-none transition focus:border-teal-700 focus:ring-2 focus:ring-teal-100"
              maxLength={4000}
              value={skills}
              onChange={(event) => setSkills(event.target.value)}
            />
          </label>
          <label className="block">
            <span className="text-sm font-medium text-zinc-800">Years of experience</span>
            <input
              className="mt-2 w-full rounded border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-950 outline-none transition focus:border-teal-700 focus:ring-2 focus:ring-teal-100"
              min="0"
              max="80"
              step="0.5"
              type="number"
              value={yearsExperience}
              onChange={(event) => setYearsExperience(event.target.value)}
            />
          </label>
          <label className="block">
            <span className="text-sm font-medium text-zinc-800">Experience</span>
            <textarea
              className="mt-2 min-h-36 w-full rounded border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-950 outline-none transition focus:border-teal-700 focus:ring-2 focus:ring-teal-100"
              maxLength={15000}
              value={experience}
              onChange={(event) => setExperience(event.target.value)}
            />
          </label>
          <label className="block">
            <span className="text-sm font-medium text-zinc-800">Education</span>
            <textarea
              className="mt-2 min-h-36 w-full rounded border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-950 outline-none transition focus:border-teal-700 focus:ring-2 focus:ring-teal-100"
              maxLength={15000}
              value={education}
              onChange={(event) => setEducation(event.target.value)}
            />
          </label>
        </div>
        <div className="mt-6 flex flex-wrap gap-3">
          <button
            className="rounded bg-zinc-950 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-zinc-800 disabled:cursor-not-allowed disabled:bg-zinc-400"
            disabled={saving}
            type="submit"
          >
            {saving ? "Saving..." : "Save profile"}
          </button>
          <Link className="rounded border border-zinc-300 bg-white px-4 py-2.5 text-sm text-zinc-900" href={`/resumes/${resumeId}/profile`}>
            Cancel
          </Link>
        </div>
      </form>
    );
  }

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <section className="rounded border border-zinc-200 bg-white p-6 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-sm text-zinc-600">{resume.original_filename}</p>
            <h1 className="mt-1 text-2xl font-semibold text-zinc-950">Extracted Profile</h1>
            <p className="mt-2 text-sm text-zinc-600">Processed {formatDateTime(extraction.processed_at)}</p>
          </div>
          <Link className="rounded bg-zinc-950 px-4 py-2.5 text-sm font-medium text-white" href={`/resumes/${resumeId}/profile/edit`}>
            Edit
          </Link>
        </div>
      </section>
      <section className="rounded border border-zinc-200 bg-white p-6 shadow-sm">
        <h2 className="text-lg font-semibold text-zinc-950">Skills</h2>
        <ItemList items={extraction.skills} empty="No skills extracted yet." />
      </section>
      <section className="rounded border border-zinc-200 bg-white p-6 shadow-sm">
        <h2 className="text-lg font-semibold text-zinc-950">Experience</h2>
        <p className="mt-2 text-sm text-zinc-700">
          Years of experience: {calculateTotalExperienceDuration(extraction.experience)}
        </p>
        {extraction.experience.length === 0 ? (
          <p className="mt-3 text-sm text-zinc-600">No experience entries extracted yet.</p>
        ) : (
          <ul className="mt-3 space-y-3">
            {extraction.experience.map((item, index) => (
              <li
                key={index}
                className="space-y-1 rounded border border-zinc-200 bg-zinc-50 p-3 text-sm text-zinc-800"
              >
                <p>
                  <span className="font-medium text-zinc-950">Role:</span>{" "}
                  {String(item.title ?? "Not provided")}
                </p>
                <p>
                  <span className="font-medium text-zinc-950">Company:</span>{" "}
                  {String(item.company ?? "Not provided")}
                </p>
                <p>
                  <span className="font-medium text-zinc-950">Duration:</span>{" "}
                  {formatYearsToDuration(item.years)}
                </p>
              </li>
            ))}
          </ul>
        )}
      </section>
      <section className="rounded border border-zinc-200 bg-white p-6 shadow-sm">
        <h2 className="text-lg font-semibold text-zinc-950">Education</h2>
        {extraction.education.length === 0 ? (
          <p className="mt-3 text-sm text-zinc-600">No education entries extracted yet.</p>
        ) : (
          <ul className="mt-3 space-y-3">
            {extraction.education.map((item, index) => (
              <li
                key={index}
                className="space-y-1 rounded border border-zinc-200 bg-zinc-50 p-3 text-sm text-zinc-800"
              >
                <p>
                  <span className="font-medium text-zinc-950">Institution:</span>{" "}
                  {String(item.institution ?? "Not provided")}
                </p>
                <p>
                  <span className="font-medium text-zinc-950">Qualification:</span>{" "}
                  {String(
                    [item.credential, item.field]
                      .filter(Boolean)
                      .join(", ") || "Not provided"
                  )}
                </p>
                <p>
                  <span className="font-medium text-zinc-950">Year of graduation:</span>{" "}
                  {String(item.year ?? "Not provided")}
                </p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
