"use client";

import { FormEvent, useEffect, useState } from "react";
import { apiFetch, type JobRoleListResponse, type JobRoleSummary, type SalaryTrendResponse } from "@/lib/api";
import { SalaryTrendChart } from "@/components/SalaryTrendChart";

export function SalaryTrendPanel() {
  const [trend, setTrend] = useState<SalaryTrendResponse | null>(null);
  const [roles, setRoles] = useState<JobRoleSummary[]>([]);
  const [role, setRole] = useState("");
  const [loading, setLoading] = useState(false);
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
      .catch(() => {
        if (active) {
          setRoles([]);
        }
      });
    return () => {
      active = false;
    };
  }, []);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    const formData = new FormData(event.currentTarget);
    const selectedRole = String(formData.get("role") ?? "").trim();
    const months = String(formData.get("months") ?? "12");
    if (!/^[\p{L}\p{N}_\s.,&()+#/'-]{2,100}$/u.test(selectedRole)) {
      setError("Enter a valid role using letters, numbers, spaces, and common punctuation.");
      setLoading(false);
      return;
    }
    if (!["3", "6", "12", "24"].includes(months)) {
      setError("Choose a valid month range.");
      setLoading(false);
      return;
    }
    try {
      const response = await apiFetch<SalaryTrendResponse>(
        `/salary-trends?role=${encodeURIComponent(selectedRole)}&months=${encodeURIComponent(months)}`
      );
      setTrend(response);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to load salary trends.");
      setTrend(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="grid gap-6 lg:grid-cols-[340px_1fr]">
      <form className="rounded border border-zinc-200 bg-white p-5 shadow-sm" onSubmit={onSubmit}>
        <h1 className="text-xl font-semibold text-zinc-950">Salary trend chart</h1>
        <p className="mt-1 text-sm leading-6 text-zinc-600">
          Compare monthly average salary from stored job postings that include salary ranges.
        </p>

        <label className="mt-5 block">
          <span className="text-sm font-medium text-zinc-800">Job role</span>
          <input
            className="mt-2 w-full rounded border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:border-teal-700 focus:ring-2 focus:ring-teal-100"
            list="salary-role-options"
            name="role"
            onChange={(event) => setRole(event.target.value)}
            placeholder={roles[0]?.name ?? "Software Engineer"}
            required
            minLength={2}
            maxLength={100}
            value={role}
          />
          <datalist id="salary-role-options">
            {roles.map((item) => (
              <option key={item.slug} value={item.name} />
            ))}
          </datalist>
        </label>

        <label className="mt-4 block">
          <span className="text-sm font-medium text-zinc-800">Months</span>
          <select
            className="mt-2 w-full rounded border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:border-teal-700 focus:ring-2 focus:ring-teal-100"
            name="months"
            defaultValue="12"
          >
            <option value="3">3 months</option>
            <option value="6">6 months</option>
            <option value="12">12 months</option>
            <option value="24">24 months</option>
          </select>
        </label>

        <button
          className="mt-5 w-full rounded bg-zinc-950 px-4 py-2.5 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-zinc-400"
          disabled={loading}
          type="submit"
        >
          {loading ? "Loading..." : "View trend"}
        </button>

        {error ? <p className="mt-4 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-900">{error}</p> : null}
      </form>

      <article className="rounded border border-zinc-200 bg-white p-6 shadow-sm">
        {!trend ? (
          <p className="text-sm text-zinc-600">Search for a role to view salary trend data.</p>
        ) : trend.points.length === 0 ? (
          <div>
            <h2 className="text-2xl font-semibold text-zinc-950">{trend.role}</h2>
            <p className="mt-3 text-sm leading-6 text-zinc-600">
              No salary trend data is available for this role yet. The chart needs stored job postings with salary ranges.
            </p>
          </div>
        ) : (
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-teal-700">
              {trend.sample_size} salary samples
            </p>
            <h2 className="mt-2 text-2xl font-semibold text-zinc-950">{trend.role}</h2>
            <p className="mt-1 text-sm text-zinc-600">Average {trend.period} salary by posting month.</p>

            <div className="mt-8">
              <SalaryTrendChart points={trend.points} currency={trend.currency} />
            </div>
          </div>
        )}
      </article>
    </section>
  );
}
