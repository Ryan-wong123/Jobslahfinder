"use client";

import type { ExperienceBand, SalaryExperienceBand } from "@/lib/api";

type Props = { bands: SalaryExperienceBand[]; currency: string; selectedBand: ExperienceBand };

const money = (value: number, currency: string) => new Intl.NumberFormat("en-SG", {
  style: "currency", currency, maximumFractionDigits: 0
}).format(value);

export function SalaryTrendChart({ bands, currency, selectedBand }: Props) {
  const width = 760, height = 320;
  const padding = { top: 30, right: 30, bottom: 62, left: 88 };
  const chartHeight = height - padding.top - padding.bottom;
  const values = bands.flatMap((band) => [band.lower_quartile, band.upper_quartile].filter((value): value is number => value !== null));
  const maximum = Math.max(1, ...values) * 1.1;
  const y = (value: number) => padding.top + chartHeight - (value / maximum) * chartHeight;
  const slot = (width - padding.left - padding.right) / bands.length;

  return <div className="overflow-x-auto rounded border border-zinc-200 bg-white">
    <svg aria-label="Salary comparison by experience band" className="min-w-[640px]" role="img" viewBox={`0 0 ${width} ${height}`}>
      <rect fill="white" width={width} height={height} />
      {[0, .25, .5, .75, 1].map((fraction) => <g key={fraction}>
        <line stroke="#e4e4e7" x1={padding.left} x2={width-padding.right} y1={y(maximum*fraction)} y2={y(maximum*fraction)} />
        <text fill="#52525b" fontSize="11" textAnchor="end" x={padding.left-10} y={y(maximum*fraction)+4}>{money(maximum*fraction, currency)}</text>
      </g>)}
      {bands.map((band, index) => {
        const x = padding.left + slot * (index + .5);
        const selected = band.band === selectedBand;
        return <g key={band.band} aria-label={`${band.label}, ${band.sample_count} samples`}>
          {band.lower_quartile !== null && band.upper_quartile !== null && band.median_salary !== null ? <>
            <rect x={x-34} y={y(band.upper_quartile)} width="68" height={Math.max(2, y(band.lower_quartile)-y(band.upper_quartile))} rx="4" fill={selected ? "#0f766e" : "#99f6e4"} />
            <line stroke={selected ? "white" : "#0f766e"} strokeWidth="3" x1={x-34} x2={x+34} y1={y(band.median_salary)} y2={y(band.median_salary)} />
          </> : <text fill="#71717a" fontSize="12" textAnchor="middle" x={x} y={padding.top+chartHeight/2}>No data</text>}
          <text fill={selected ? "#0f766e" : "#3f3f46"} fontSize="12" fontWeight={selected ? "700" : "500"} textAnchor="middle" x={x} y={height-35}>{band.label}</text>
          <text fill="#71717a" fontSize="11" textAnchor="middle" x={x} y={height-18}>{band.sample_count} sample{band.sample_count === 1 ? "" : "s"}</text>
        </g>;
      })}
    </svg>
  </div>;
}
