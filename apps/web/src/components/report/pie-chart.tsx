"use client";

import { formatNumber } from "@/lib/format";
import type { Locale } from "@/i18n/routing";
import type { Bilingual } from "@/lib/api/types";

const SERIES = [
  "var(--series-1)",
  "var(--series-2)",
  "var(--series-3)",
  "var(--series-4)",
  "var(--series-5)",
];

/**
 * A share of a whole, as SVG arcs.
 *
 * Direction is fixed rather than inherited from the writing mode: a pie that
 * mirrors under RTL would put the largest slice somewhere different on the same
 * data. Every slice is named with its value and share in the legend, so the figure
 * never depends on distinguishing two colours — the same relief rule the bar chart
 * follows, and what makes the palette safe in light mode.
 */
export function PieChart({
  title,
  categories,
  values,
  locale,
  donut = false,
}: {
  title: Bilingual;
  categories: string[];
  values: number[];
  locale: string;
  donut?: boolean;
}) {
  const key = locale as Locale;
  const label = title[key] || title.en;
  const total = values.reduce((sum, value) => sum + value, 0);

  const radius = 42;
  const circumference = 2 * Math.PI * radius;
  let offset = 0;

  const slices = values.map((value, index) => {
    const share = total > 0 ? value / total : 0;
    const slice = {
      length: share * circumference,
      offset,
      color: SERIES[index % SERIES.length],
      share,
    };
    offset += slice.length;
    return slice;
  });

  return (
    <figure
      role="img"
      aria-label={label}
      className="flex h-full flex-col rounded-lg border border-border bg-surface p-5"
    >
      <figcaption className="mb-4 text-sm font-medium">{label}</figcaption>

      <div className="flex flex-1 flex-col items-center gap-4 sm:flex-row sm:items-center">
        <svg viewBox="0 0 100 100" className="h-32 w-32 shrink-0 -rotate-90">
          {slices.map((slice, index) => (
            <circle
              key={index}
              cx="50"
              cy="50"
              r={radius}
              fill="none"
              stroke={slice.color}
              strokeWidth={donut ? 12 : radius * 2}
              // A full-radius stroke fills the circle, so one shape draws both forms.
              strokeDasharray={`${slice.length} ${circumference - slice.length}`}
              strokeDashoffset={-slice.offset}
            />
          ))}
          {donut ? (
            <text
              transform="rotate(90 50 50)"
              x="50"
              y="50"
              textAnchor="middle"
              dominantBaseline="central"
              className="fill-foreground text-[13px] font-medium tabular-nums"
            >
              {formatNumber(total, locale)}
            </text>
          ) : null}
        </svg>

        <ul className="flex w-full flex-col gap-1.5">
          {categories.map((category, index) => (
            <li key={`${category}-${index}`} className="flex items-center gap-2 text-xs">
              <span
                aria-hidden
                className="size-2.5 shrink-0 rounded-sm"
                style={{ background: slices[index]?.color }}
              />
              <span className="min-w-0 flex-1 truncate text-muted" title={category}>
                {category}
              </span>
              <span className="tabular-nums text-foreground">
                {formatNumber(values[index], locale)}
              </span>
              <span className="w-10 text-end tabular-nums text-muted">
                {formatNumber(Math.round((slices[index]?.share ?? 0) * 100), locale)}%
              </span>
            </li>
          ))}
        </ul>
      </div>
    </figure>
  );
}
