"use client";

import { FormEvent, useEffect, useState } from "react";
import { apiFetch, type JobRoleListResponse, type JobRoleSummary, type SalaryComparisonResponse } from "@/lib/api";

export function SalaryTrendPanel() {
  const [comparison, setComparison] = useState<SalaryComparisonResponse | null>(null);
  const [roles, setRoles] = useState<JobRoleSummary[]>([]);
  const [role, setRole] = useState("");
  const [secondRole, setSecondRole] = useState("");
  const [thirdRole, setThirdRole] = useState("");
  const [fourthRole, setFourthRole] = useState("");
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
    const selectedRoles = ["role", "secondRole", "thirdRole", "fourthRole"]
      .map((name) => String(formData.get(name) ?? "").trim()).filter(Boolean);
    const uniqueRoles = new Set(selectedRoles.map((item) => item.toLocaleLowerCase()));
    if (selectedRoles.length < 2 || selectedRoles.length > 4 || selectedRoles.some((item) => !/^[\p{L}\p{N}_\s.,&()+#\/'-]{2,100}$/u.test(item)) || uniqueRoles.size !== selectedRoles.length) {
      setError("Choose between two and four different valid job roles.");
      setLoading(false);
      return;
    }
    try {
      const response = await apiFetch<SalaryComparisonResponse>(
        `/jobs/salary-comparison?${selectedRoles.map((item) => `roles=${encodeURIComponent(item)}`).join("&")}`
      );
      setComparison(response);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to load salary trends.");
      setComparison(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="grid gap-6 lg:grid-cols-[340px_1fr]">
      <form className="rounded border border-zinc-200 bg-white p-5 shadow-sm" onSubmit={onSubmit}>
        <h1 className="text-xl font-semibold text-zinc-950">Salary comparison</h1>
        <p className="mt-1 text-sm leading-6 text-zinc-600">
          Compare normalized monthly SGD salary and minimum-experience data for two to four roles.
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
          <span className="text-sm font-medium text-zinc-800">Compare with</span>
          <input className="mt-2 w-full rounded border border-zinc-300 bg-white px-3 py-2 text-sm" list="salary-role-options" name="secondRole" onChange={(event) => setSecondRole(event.target.value)} required minLength={2} maxLength={100} value={secondRole} />
        </label>
        <label className="mt-4 block">
          <span className="text-sm font-medium text-zinc-800">Third role (optional)</span>
          <input className="mt-2 w-full rounded border border-zinc-300 bg-white px-3 py-2 text-sm" list="salary-role-options" name="thirdRole" onChange={(event) => setThirdRole(event.target.value)} minLength={2} maxLength={100} value={thirdRole} />
        </label>
        <label className="mt-4 block">
          <span className="text-sm font-medium text-zinc-800">Fourth role (optional)</span>
          <input className="mt-2 w-full rounded border border-zinc-300 bg-white px-3 py-2 text-sm" list="salary-role-options" name="fourthRole" onChange={(event) => setFourthRole(event.target.value)} minLength={2} maxLength={100} value={fourthRole} />
        </label>

        <button
          className="mt-5 w-full rounded bg-zinc-950 px-4 py-2.5 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-zinc-400"
          disabled={loading}
          type="submit"
        >
          {loading ? "Loading..." : "Compare roles"}
        </button>

        {error ? <p className="mt-4 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-900">{error}</p> : null}
      </form>

      <article className="rounded border border-zinc-200 bg-white p-6 shadow-sm">
        {!comparison ? (
          <p className="text-sm text-zinc-600">Choose two roles to compare their salary and experience requirements.</p>
        ) : comparison.items.length === 0 ? (
          <div>
            <h2 className="text-2xl font-semibold text-zinc-950">Not enough salary data</h2>
            <p className="mt-3 text-sm leading-6 text-zinc-600">
              Each role needs at least {comparison.minimum_sample_size} valid salary postings before statistics are shown.
            </p>
          </div>
        ) : (
          <div>
            <h2 className="text-2xl font-semibold text-zinc-950">Monthly salary comparison</h2>
            <div className="mt-6 grid gap-4 sm:grid-cols-2">{comparison.items.map((item) => (
              <section className="rounded border border-zinc-200 p-4" key={item.role}>
                <h3 className="font-semibold text-zinc-950">{item.role}</h3>
                <p className="mt-3 text-2xl font-semibold text-teal-700">SGD {item.median_salary.toLocaleString("en-SG")}</p>
                <p className="text-xs text-zinc-500">median monthly salary · {item.valid_posting_count} postings</p>
                <p className="mt-3 text-sm text-zinc-700">Range: SGD {item.minimum_salary.toLocaleString("en-SG")}–{item.maximum_salary.toLocaleString("en-SG")}</p>
                <p className="mt-1 text-sm text-zinc-700">Average: SGD {item.average_salary.toLocaleString("en-SG")}</p>
                <p className="mt-1 text-sm text-zinc-700">Median minimum experience: {item.median_minimum_experience_years === null ? "Not available" : `${item.median_minimum_experience_years} years`}</p>
                <p className="mt-1 text-xs text-zinc-500">Experience coverage: {Math.round(item.experience_coverage * 100)}%</p>
              </section>
            ))}</div>
            {comparison.insufficient_sample_roles.length ? <p className="mt-4 text-sm text-amber-800">Not shown due to insufficient samples: {comparison.insufficient_sample_roles.join(", ")}.</p> : null}
          </div>
        )}
      </article>
    </section>
  );
}
