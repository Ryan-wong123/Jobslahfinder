"use client";

import { FormEvent, useEffect, useState } from "react";
import { apiFetch, type ExperienceBand, type JobRoleListResponse, type JobRoleSummary, type SalaryExperienceComparisonResponse } from "@/lib/api";
import { SalaryTrendChart } from "@/components/SalaryTrendChart";

const bandOptions: { value: ExperienceBand; label: string }[] = [
  { value: "0-2", label: "0–2 years" }, { value: "3-5", label: "3–5 years" },
  { value: "6-9", label: "6–9 years" }, { value: "10+", label: "10+ years" }
];
const money = (value: number, currency: string) => new Intl.NumberFormat("en-SG", { style: "currency", currency, maximumFractionDigits: 0 }).format(value);

export function SalaryTrendPanel() {
  const [comparison, setComparison] = useState<SalaryExperienceComparisonResponse | null>(null);
  const [roles, setRoles] = useState<JobRoleSummary[]>([]);
  const [role, setRole] = useState("");
  const [band, setBand] = useState<ExperienceBand>("0-2");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { let active = true; apiFetch<JobRoleListResponse>("/job-roles").then((response) => active && setRoles(response.items)).catch(() => active && setRoles([])); return () => { active = false; }; }, []);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setLoading(true); setError(null);
    const selectedRole = role.trim();
    if (!/^[\p{L}\p{N}_\s.,&()+#\/'-]{2,100}$/u.test(selectedRole)) { setError("Enter a valid role using letters, numbers, spaces, and common punctuation."); setLoading(false); return; }
    if (!bandOptions.some((option) => option.value === band)) { setError("Choose a valid experience band."); setLoading(false); return; }
    try {
      setComparison(await apiFetch<SalaryExperienceComparisonResponse>(`/salary-comparison?role=${encodeURIComponent(selectedRole)}&experience_band=${encodeURIComponent(band)}`));
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Unable to load salary comparison."); setComparison(null); }
    finally { setLoading(false); }
  }

  const selected = comparison?.bands.find((item) => item.band === comparison.selected_band);
  return <section className="grid gap-6 lg:grid-cols-[340px_1fr]">
    <form className="rounded border border-zinc-200 bg-white p-5 shadow-sm" onSubmit={onSubmit}>
      <h1 className="text-xl font-semibold text-zinc-950">Salary by experience</h1>
      <p className="mt-1 text-sm leading-6 text-zinc-600">Compare normalized monthly SGD advertised salaries across experience bands.</p>
      <label className="mt-5 block"><span className="text-sm font-medium">Job role</span><input className="mt-2 w-full rounded border px-3 py-2 text-sm" list="salary-role-options" value={role} onChange={(event) => setRole(event.target.value)} required minLength={2} maxLength={100} placeholder={roles[0]?.name ?? "Software Engineer"} /><datalist id="salary-role-options">{roles.map((item) => <option key={item.slug} value={item.name} />)}</datalist></label>
      <label className="mt-4 block"><span className="text-sm font-medium">Experience band</span><select className="mt-2 w-full rounded border px-3 py-2 text-sm" value={band} onChange={(event) => setBand(event.target.value as ExperienceBand)}>{bandOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
      <button className="mt-5 w-full rounded bg-zinc-950 px-4 py-2.5 text-sm font-medium text-white disabled:bg-zinc-400" disabled={loading} type="submit">{loading ? "Loading..." : "Compare salaries"}</button>
      {error ? <p className="mt-4 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-900">{error}</p> : null}
    </form>
    <article className="rounded border border-zinc-200 bg-white p-6 shadow-sm">
      {!comparison ? <p className="text-sm text-zinc-600">Select a role and experience band to compare advertised salaries.</p> : comparison.role_sample_count === 0 ? <div><h2 className="text-2xl font-semibold">{comparison.role}</h2><p className="mt-3 text-sm text-zinc-600">No qualifying published SGD salary data with specified experience is available for this role.</p><p className="mt-4 text-xs text-zinc-500">{comparison.disclaimer}</p></div> : <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-teal-700">{comparison.role_sample_count} qualifying postings</p><h2 className="mt-2 text-2xl font-semibold">{comparison.role}</h2>
        <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4"><Stat label="Selected band" value={selected?.label ?? "—"} /><Stat label="Median" value={selected?.median_salary == null ? "No data" : money(selected.median_salary, comparison.currency)} /><Stat label="Advertised range (Q1–Q3)" value={selected?.lower_quartile == null || selected.upper_quartile == null ? "No data" : `${money(selected.lower_quartile, comparison.currency)}–${money(selected.upper_quartile, comparison.currency)}`} /><Stat label="Vs role median" value={comparison.selected_band_difference_from_role_median == null ? "No data" : `${comparison.selected_band_difference_from_role_median >= 0 ? "+" : ""}${money(comparison.selected_band_difference_from_role_median, comparison.currency)}`} /></div>
        <p className="mt-4 text-sm text-zinc-600">Selected band: {selected?.sample_count ?? 0} qualifying posting{selected?.sample_count === 1 ? "" : "s"}. Role-wide median: {comparison.role_median_salary == null ? "No data" : money(comparison.role_median_salary, comparison.currency)}.</p>
        <div className="mt-7"><SalaryTrendChart bands={comparison.bands} currency={comparison.currency} selectedBand={comparison.selected_band} /></div><p className="mt-4 text-xs text-zinc-500">{comparison.disclaimer}</p>
      </div>}
    </article>
  </section>;
}

function Stat({ label, value }: { label: string; value: string }) { return <div className="rounded border border-zinc-200 p-3"><p className="text-xs text-zinc-500">{label}</p><p className="mt-1 font-semibold text-zinc-950">{value}</p></div>; }
