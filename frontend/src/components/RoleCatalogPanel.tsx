"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { apiFetch, type JobRoleListResponse, type JobRoleSummary } from "@/lib/api";

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

export function RoleCatalogPanel() {
  const [roles, setRoles] = useState<JobRoleSummary[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    apiFetch<JobRoleListResponse>("/job-roles")
      .then((response) => {
        if (active) {
          setRoles(response.items);
          setError(null);
        }
      })
      .catch((caught) => {
        if (active) {
          setError(caught instanceof Error ? caught.message : "Unable to load job roles.");
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
  }, []);

  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) {
      return roles;
    }
    return roles.filter(
      (role) =>
        role.name.toLowerCase().includes(normalized) ||
        role.category.toLowerCase().includes(normalized) ||
        role.tagline.toLowerCase().includes(normalized)
    );
  }, [query, roles]);

  return (
    <section>
      <div className="mb-8 max-w-3xl">
        <p className="text-sm font-semibold uppercase tracking-wide text-teal-700">Career roadmap</p>
        <h1 className="mt-3 text-3xl font-semibold text-zinc-950">Explore job roles</h1>
        <p className="mt-3 text-base leading-7 text-zinc-600">
          Browse role guides with responsibilities, learning steps, live job counts, salary signals, and matching jobs from the platform.
        </p>
      </div>

      <label className="mb-6 block max-w-xl">
        <span className="text-sm font-medium text-zinc-800">Search roles</span>
        <input
          className="mt-2 w-full rounded border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:border-teal-700 focus:ring-2 focus:ring-teal-100"
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Security, software, data..."
          value={query}
        />
      </label>

      {loading ? <p className="rounded border border-zinc-200 bg-white p-5 text-sm text-zinc-600">Loading roles...</p> : null}
      {error ? <p className="rounded border border-red-200 bg-red-50 p-5 text-sm text-red-900">{error}</p> : null}

      <div className="grid gap-4 md:grid-cols-2">
        {filtered.map((role) => (
          <Link
            className="rounded border border-zinc-200 bg-white p-5 shadow-sm transition hover:border-teal-700 hover:shadow-md"
            href={`/roadmaps/${role.slug}`}
            key={role.slug}
          >
            <p className="text-xs font-semibold uppercase tracking-wide text-teal-700">{role.category}</p>
            <h2 className="mt-2 text-xl font-semibold text-zinc-950">{role.name}</h2>
            <p className="mt-2 min-h-12 text-sm leading-6 text-zinc-600">{role.tagline}</p>
            <dl className="mt-5 grid grid-cols-2 gap-3 border-t border-zinc-100 pt-4 text-sm">
              <div>
                <dt className="text-zinc-500">Jobs now</dt>
                <dd className="mt-1 font-semibold text-zinc-950">{role.job_count}</dd>
              </div>
              <div>
                <dt className="text-zinc-500">Typical salary</dt>
                <dd className="mt-1 font-semibold text-zinc-950">{formatSalary(role.typical_monthly_salary)}</dd>
              </div>
            </dl>
          </Link>
        ))}
      </div>

      {!loading && !error && filtered.length === 0 ? (
        <p className="rounded border border-zinc-200 bg-white p-5 text-sm text-zinc-600">No roles match your search.</p>
      ) : null}
    </section>
  );
}
