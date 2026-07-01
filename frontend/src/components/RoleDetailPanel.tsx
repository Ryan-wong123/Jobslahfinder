"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiFetch, formatDate, type JobRoleDetail } from "@/lib/api";
import { SalaryTrendChart } from "@/components/SalaryTrendChart";

function formatSalary(value: number | null): string {
  if (value === null) {
    return "N/A";
  }
  return new Intl.NumberFormat("en-SG", {
    style: "currency",
    currency: "SGD",
    maximumFractionDigits: 0
  }).format(value);
}

export function RoleDetailPanel({ slug }: { slug: string }) {
  const [role, setRole] = useState<JobRoleDetail | null>(null);
  const [tab, setTab] = useState<"overview" | "salary">("overview");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    apiFetch<JobRoleDetail>(`/job-roles/${encodeURIComponent(slug)}`)
      .then((response) => {
        if (active) {
          setRole(response);
          setError(null);
        }
      })
      .catch((caught) => {
        if (active) {
          setError(caught instanceof Error ? caught.message : "Unable to load role.");
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
  }, [slug]);

  if (loading) {
    return <p className="mx-auto max-w-5xl px-6 py-10 text-sm text-zinc-600">Loading role...</p>;
  }
  if (error || !role) {
    return <p className="mx-auto max-w-5xl px-6 py-10 text-sm text-red-700">{error ?? "Role not found."}</p>;
  }

  return (
    <article className="mx-auto min-h-screen max-w-6xl px-6 py-8">
      <header className="mb-8 flex flex-wrap items-center justify-between gap-4 border-b border-zinc-200 pb-5">
        <Link href="/" className="text-sm font-semibold text-zinc-950">
          Secure Job Platform
        </Link>
        <nav className="flex items-center gap-2 text-sm">
          <Link className="rounded px-3 py-2 text-zinc-700 hover:bg-zinc-100" href="/roadmaps">
            Roles
          </Link>
          <Link className="rounded px-3 py-2 text-zinc-700 hover:bg-zinc-100" href="/jobs">
            Jobs
          </Link>
          <Link className="rounded px-3 py-2 text-zinc-700 hover:bg-zinc-100" href="/account">
            Account
          </Link>
        </nav>
      </header>

      <section className="border-b border-zinc-200 pb-8">
        <Link className="text-sm font-medium text-teal-800 hover:text-teal-950" href="/roadmaps">
          Back to roles
        </Link>
        <p className="mt-6 text-sm font-semibold uppercase tracking-wide text-teal-700">{role.category}</p>
        <h1 className="mt-3 text-4xl font-semibold leading-tight text-zinc-950">{role.name}</h1>
        <p className="mt-4 max-w-3xl text-base leading-7 text-zinc-600">{role.tagline}</p>
      </section>

      <nav className="flex border-b border-zinc-200">
        <button
          className={`px-5 py-4 text-sm font-medium ${tab === "overview" ? "border-b-4 border-teal-700 text-teal-800" : "text-zinc-600"}`}
          onClick={() => setTab("overview")}
          type="button"
        >
          Overview
        </button>
        <button
          className={`px-5 py-4 text-sm font-medium ${tab === "salary" ? "border-b-4 border-teal-700 text-teal-800" : "text-zinc-600"}`}
          onClick={() => setTab("salary")}
          type="button"
        >
          Salary
        </button>
      </nav>

      <section className="py-10">
        <div className="grid gap-4 md:grid-cols-3">
          <div className="rounded border border-zinc-200 bg-white p-6 text-center shadow-sm">
            <h2 className="text-base font-semibold text-zinc-950">Job opportunities</h2>
            <p className="mt-3 text-3xl font-light text-zinc-950">{role.job_count.toLocaleString("en-SG")}</p>
            <p className="mt-1 text-sm text-zinc-700">Jobs in Singapore right now</p>
          </div>
          <div className="rounded border border-zinc-200 bg-white p-6 text-center shadow-sm">
            <h2 className="text-base font-semibold text-zinc-950">Salary</h2>
            <p className="mt-3 text-3xl font-light text-zinc-950">{formatSalary(role.typical_monthly_salary)}</p>
            <p className="mt-1 text-sm text-zinc-700">Typical monthly salary in Singapore</p>
          </div>
          <div className="rounded border border-zinc-200 bg-white p-6 text-center shadow-sm">
            <h2 className="text-base font-semibold text-zinc-950">Top skills</h2>
            <p className="mt-3 text-3xl font-light text-zinc-950">{role.top_skills.length}</p>
            <p className="mt-1 text-sm text-zinc-700">Signals from stored postings</p>
          </div>
        </div>

        {tab === "overview" ? (
          <div className="mt-12 space-y-10">
            <section>
              <h2 className="text-2xl font-semibold text-zinc-950">On this page</h2>
              <ul className="mt-4 list-disc space-y-1 pl-5 text-sm">
                <li>
                  <a className="font-medium underline" href="#overview">
                    What's it like to be a {role.name}?
                  </a>
                </li>
                <li>
                  <a className="font-medium underline" href="#become">
                    How to become a {role.name}
                  </a>
                </li>
                <li>
                  <a className="font-medium underline" href="#jobs">
                    Latest {role.name} jobs
                  </a>
                </li>
                <li>
                  <a className="font-medium underline" href="#skills">
                    Top skills and experience
                  </a>
                </li>
              </ul>
            </section>

            <section id="overview">
              <h2 className="text-2xl font-semibold text-zinc-950">What's it like to be a {role.name}?</h2>
              <p className="mt-5 text-base leading-7 text-zinc-800">{role.overview}</p>
              <h3 className="mt-8 text-xl font-medium text-zinc-950">Tasks and duties</h3>
              <ul className="mt-4 list-disc space-y-2 pl-5 text-base leading-7 text-zinc-800">
                {role.tasks.map((task) => (
                  <li key={task}>{task}</li>
                ))}
              </ul>
            </section>

            <section id="become" className="border-t border-zinc-200 pt-10">
              <h2 className="text-3xl font-semibold text-zinc-950">How to become a {role.name}</h2>
              <p className="mt-5 text-xl leading-8 text-zinc-800">{role.how_to_become_intro}</p>
              <ol className="mt-8 list-decimal space-y-3 pl-7 text-xl leading-8 text-zinc-800">
                {role.how_to_become_steps.map((step) => (
                  <li key={step}>{step}</li>
                ))}
              </ol>
            </section>

            <section id="jobs" className="border-t border-zinc-200 pt-10">
              <h2 className="text-2xl font-semibold text-zinc-950">Latest {role.name} jobs</h2>
              <div className="mt-5 space-y-3">
                {role.latest_jobs.length === 0 ? (
                  <p className="rounded border border-zinc-200 bg-white p-4 text-sm text-zinc-600">No matching jobs are available yet.</p>
                ) : (
                  role.latest_jobs.map((job) => (
                    <Link className="block rounded border border-zinc-200 bg-white p-4 hover:border-teal-700" href={`/jobs/${job.id}`} key={job.id}>
                      <span className="block font-semibold text-zinc-950">{job.title}</span>
                      <span className="mt-1 block text-sm text-zinc-600">
                        {job.company} - {job.location ?? "Singapore"} - Posted {formatDate(job.posting_date)}
                      </span>
                    </Link>
                  ))
                )}
              </div>
            </section>

            <section id="skills" className="border-t border-zinc-200 pt-10">
              <h2 className="text-2xl font-semibold text-zinc-950">Top skills and experience for {role.name}s</h2>
              <div className="mt-5 flex flex-wrap gap-2">
                {role.top_skills.map((skill) => (
                  <span className="rounded border border-zinc-200 bg-zinc-50 px-3 py-1.5 text-sm text-zinc-700" key={skill}>
                    {skill}
                  </span>
                ))}
              </div>
            </section>
          </div>
        ) : (
          <section className="mt-12">
            <h2 className="text-2xl font-semibold text-zinc-950">{role.name} salary trend</h2>
            {role.salary_points.length === 0 ? (
              <p className="mt-5 rounded border border-zinc-200 bg-white p-5 text-sm text-zinc-600">
                No salary trend data is available for this role yet. The chart needs stored job postings with salary ranges.
              </p>
            ) : (
              <div className="mt-8">
                <SalaryTrendChart points={role.salary_points} currency="SGD" />
              </div>
            )}
          </section>
        )}
      </section>
    </article>
  );
}
