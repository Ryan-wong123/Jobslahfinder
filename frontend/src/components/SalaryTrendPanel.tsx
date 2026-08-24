"use client";

import { FormEvent, useEffect, useState } from "react";
import { apiFetch, formatDate, type ExperienceSalaryComparison, type JobRoleListResponse, type JobRoleSummary, type SalaryTrendResponse } from "@/lib/api";
import { ExperienceSalaryChart, SalaryTrendChart } from "@/components/SalaryTrendChart";

export function SalaryTrendPanel() {
  const [trend, setTrend] = useState<SalaryTrendResponse | null>(null);
  const [roles, setRoles] = useState<JobRoleSummary[]>([]);
  const [role, setRole] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [comparison, setComparison] = useState<ExperienceSalaryComparison | null>(null);
  const [view, setView] = useState<"historical" | "experience">("historical");

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
    const location = String(formData.get("location") ?? "").trim();
    if (!/^[\p{L}\p{N}_\s.,&()+#\/'-]{2,100}$/u.test(selectedRole)) {
      setError("Enter a valid role using letters, numbers, spaces, and common punctuation.");
      setLoading(false);
      return;
    }
    if (!["3", "6", "12", "24"].includes(months)) {
      setError("Choose a valid month range.");
      setLoading(false);
      return;
    }
    if (location && !/^[\p{L}\p{N}_\s.,()/'-]{2,100}$/u.test(location)) {
      setError("Enter a valid location using letters, numbers, spaces, and common punctuation.");
      setLoading(false);
      return;
    }
    try {
      if (view === "experience") {
        const selected = roles.find((item) => item.name === selectedRole);
        if (!selected) throw new Error("Choose a job role from the available list.");
        const query = location ? `?location=${encodeURIComponent(location)}` : "";
        const response = await apiFetch<ExperienceSalaryComparison>(
          `/job-roles/${encodeURIComponent(selected.slug)}/salary-by-experience${query}`
        );
        setComparison(response);
      } else {
        const response = await apiFetch<SalaryTrendResponse>(
          `/salary-trends?role=${encodeURIComponent(selectedRole)}&months=${encodeURIComponent(months)}`
        );
        setTrend(response);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to load salary trends.");
      setTrend(null);
      setComparison(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="grid gap-6 lg:grid-cols-[340px_1fr]">
      <form className="rounded border border-zinc-200 bg-white p-5 shadow-sm" onSubmit={onSubmit}>
        <h1 className="text-xl font-semibold text-zinc-950">Salary Trend Chart</h1>
        <p className="mt-1 text-sm leading-6 text-zinc-600">
          Compare advertised monthly salary signals from qualifying stored job postings.
        </p>

        <fieldset className="mt-5">
          <legend className="text-sm font-medium text-zinc-800">View</legend>
          <div className="mt-2 flex gap-4 text-sm">
            <label><input checked={view === "historical"} name="view" onChange={() => setView("historical")} type="radio" /> Historical</label>
            <label><input checked={view === "experience"} name="view" onChange={() => setView("experience")} type="radio" /> By experience</label>
          </div>
        </fieldset>

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

        {view === "historical" ? <label className="mt-4 block">
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
        </label> : (
          <label className="mt-4 block">
            <span className="text-sm font-medium text-zinc-800">Location (optional)</span>
            <input className="mt-2 w-full rounded border border-zinc-300 px-3 py-2 text-sm" maxLength={100} minLength={2} name="location" placeholder="Singapore" />
          </label>
        )}

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
        {view === "experience" ? (
          comparison ? <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-teal-700">By experience</p>
            <h2 className="mt-2 text-2xl font-semibold text-zinc-950">{comparison.role_name}</h2>
            <p className="mt-1 text-sm text-zinc-600">Median advertised monthly salary{comparison.location ? ` in ${comparison.location}` : " across all locations"}.</p>
            <div className="mt-8"><ExperienceSalaryChart bands={comparison.bands} currency={comparison.currency} /></div>
            <p className="mt-5 text-xs text-zinc-600">
              Observation period: {comparison.observation_start ? formatDate(comparison.observation_start) : "No qualifying observations"}
              {comparison.observation_end ? ` to ${formatDate(comparison.observation_end)}` : ""}. Bands require at least {comparison.minimum_reliable_sample} qualifying postings.
            </p>
            <p className="mt-2 text-xs font-medium text-zinc-700">{comparison.disclaimer}</p>
          </div> : <p className="text-sm text-zinc-600">Choose a listed role to compare salary by experience.</p>
        ) : !trend ? (
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
