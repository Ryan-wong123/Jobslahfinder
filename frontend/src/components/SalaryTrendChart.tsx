"use client";

import type { ExperienceSalaryBand, SalaryTrendPoint } from "@/lib/api";

type SalaryTrendChartProps = {
  points: SalaryTrendPoint[];
  currency: string;
};

function formatSalary(value: number, currency: string): string {
  return new Intl.NumberFormat("en-SG", {
    style: "currency",
    currency,
    maximumFractionDigits: 0
  }).format(value);
}

export function SalaryTrendChart({ points, currency }: SalaryTrendChartProps) {
  const width = 760;
  const height = 300;
  const padding = { top: 28, right: 28, bottom: 54, left: 88 };
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;
  const salaries = points.map((point) => point.average_salary);
  const sampleCounts = points.map((point) => point.sample_count);
  const rawMinSalary = Math.min(...salaries);
  const rawMaxSalary = Math.max(...salaries);
  const minSalary = rawMinSalary === rawMaxSalary ? Math.max(0, rawMinSalary * 0.9) : rawMinSalary;
  const maxSalary = rawMinSalary === rawMaxSalary ? rawMaxSalary * 1.1 : rawMaxSalary;
  const salaryRange = Math.max(1, maxSalary - minSalary);
  const maxSamples = Math.max(1, ...sampleCounts);

  const xFor = (index: number) =>
    points.length === 1 ? padding.left + chartWidth / 2 : padding.left + (index / (points.length - 1)) * chartWidth;
  const yForSalary = (salary: number) => padding.top + chartHeight - ((salary - minSalary) / salaryRange) * chartHeight;
  const yForSamples = (sampleCount: number) => padding.top + chartHeight - (sampleCount / maxSamples) * (chartHeight * 0.35);
  const linePoints = points.map((point, index) => `${xFor(index)},${yForSalary(point.average_salary)}`).join(" ");
  const yTicks = Array.from({ length: 4 }, (_, index) => minSalary + (salaryRange * index) / 3);

  return (
    <div className="overflow-hidden rounded border border-zinc-200 bg-white">
      <div className="overflow-x-auto">
        <svg aria-label="Salary trend chart" className="min-w-[640px]" role="img" viewBox={`0 0 ${width} ${height}`}>
          <rect fill="#ffffff" height={height} width={width} />
          {yTicks.map((tick) => {
            const y = yForSalary(tick);
            return (
              <g key={tick}>
                <line stroke="#e4e4e7" strokeWidth="1" x1={padding.left} x2={width - padding.right} y1={y} y2={y} />
                <text fill="#52525b" fontSize="12" textAnchor="end" x={padding.left - 12} y={y + 4}>
                  {formatSalary(tick, currency)}
                </text>
              </g>
            );
          })}

          {points.map((point, index) => {
            const x = xFor(index);
            const barWidth = Math.min(38, chartWidth / Math.max(points.length * 2, 1));
            const sampleY = yForSamples(point.sample_count);
            return (
              <g key={point.period}>
                <rect
                  fill="#ccfbf1"
                  height={padding.top + chartHeight - sampleY}
                  rx="3"
                  width={barWidth}
                  x={x - barWidth / 2}
                  y={sampleY}
                />
                <text fill="#52525b" fontSize="12" textAnchor="middle" x={x} y={height - 22}>
                  {point.period}
                </text>
                <text fill="#0f766e" fontSize="11" fontWeight="600" textAnchor="middle" x={x} y={sampleY - 6}>
                  {point.sample_count}
                </text>
              </g>
            );
          })}

          {points.length > 1 ? <polyline fill="none" points={linePoints} stroke="#0f766e" strokeWidth="3" /> : null}
          {points.map((point, index) => {
            const x = xFor(index);
            const y = yForSalary(point.average_salary);
            return (
              <g key={`${point.period}-salary`}>
                <circle cx={x} cy={y} fill="#0f766e" r="5" />
                <circle cx={x} cy={y} fill="#ffffff" r="2" />
                <text fill="#18181b" fontSize="12" fontWeight="600" textAnchor="middle" x={x} y={Math.max(14, y - 12)}>
                  {formatSalary(point.average_salary, currency)}
                </text>
              </g>
            );
          })}
          <line stroke="#a1a1aa" strokeWidth="1" x1={padding.left} x2={width - padding.right} y1={padding.top + chartHeight} y2={padding.top + chartHeight} />
          <text fill="#52525b" fontSize="12" x={padding.left} y={height - 8}>
            Bar height = salary sample count
          </text>
        </svg>
      </div>

      <div className="grid border-t border-zinc-200 text-sm sm:grid-cols-3">
        {points.map((point) => (
          <div className="border-b border-zinc-100 p-3 sm:border-r" key={`${point.period}-table`}>
            <p className="font-semibold text-zinc-950">{point.period}</p>
            <p className="mt-1 text-zinc-700">{formatSalary(point.average_salary, currency)}</p>
            <p className="mt-1 text-xs text-zinc-500">{point.sample_count} sample{point.sample_count === 1 ? "" : "s"}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

export function ExperienceSalaryChart({ bands, currency }: { bands: ExperienceSalaryBand[]; currency: string }) {
  const reportable = bands.filter((band) => !band.insufficient_data && band.median_monthly_salary !== null);
  const maximum = Math.max(1, ...reportable.map((band) => band.percentile_75 ?? band.median_monthly_salary ?? 0));

  return (
    <div aria-label="Salary by experience chart" className="grid gap-4" role="img">
      {bands.map((band) => {
        const medianValue = band.median_monthly_salary;
        const medianWidth = medianValue === null ? 0 : (medianValue / maximum) * 100;
        const rangeLeft = band.percentile_25 === null ? 0 : (band.percentile_25 / maximum) * 100;
        const rangeWidth =
          band.percentile_25 === null || band.percentile_75 === null
            ? 0
            : ((band.percentile_75 - band.percentile_25) / maximum) * 100;
        return (
          <section className="rounded border border-zinc-200 p-4" key={band.key}>
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <div>
                <h3 className="font-semibold text-zinc-950">{band.label}</h3>
                <p className="text-xs text-zinc-500">{band.years}</p>
              </div>
              <p className="text-sm text-zinc-600">{band.sample_count} qualifying posting{band.sample_count === 1 ? "" : "s"}</p>
            </div>
            {band.insufficient_data ? (
              <p className="mt-3 rounded bg-amber-50 p-3 text-sm text-amber-900">Insufficient data (at least 5 postings required).</p>
            ) : (
              <>
                <div className="relative mt-4 h-9 rounded bg-zinc-100" title={`25th–75th percentile: ${formatSalary(band.percentile_25!, currency)}–${formatSalary(band.percentile_75!, currency)}`}>
                  <div className="absolute inset-y-0 left-0 rounded bg-teal-600" style={{ width: `${medianWidth}%` }} />
                  <div className="absolute top-1/2 h-2 -translate-y-1/2 rounded bg-teal-200 ring-1 ring-teal-800" style={{ left: `${rangeLeft}%`, width: `${rangeWidth}%` }} />
                </div>
                <div className="mt-2 flex flex-wrap justify-between gap-2 text-sm">
                  <strong>{formatSalary(medianValue!, currency)} median</strong>
                  <span className="text-zinc-600">25th–75th: {formatSalary(band.percentile_25!, currency)}–{formatSalary(band.percentile_75!, currency)}</span>
                  {band.difference_from_preceding_band !== null ? <span className="text-zinc-600">Previous band: {band.difference_from_preceding_band >= 0 ? "+" : ""}{formatSalary(band.difference_from_preceding_band, currency)}</span> : null}
                </div>
              </>
            )}
          </section>
        );
      })}
    </div>
  );
}
