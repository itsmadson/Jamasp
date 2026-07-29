"use client";

import { formatNumber } from "@/lib/format";
import type { Locale } from "@/i18n/routing";
import type { Bilingual } from "@/lib/api/types";

/**
 * Horizontal bars, laid out with CSS logical properties rather than SVG.
 *
 * Two reasons: bars grow from the inline-start edge, so the chart is correct in
 * RTL without a mirrored coordinate system; and Persian category labels get a
 * full line of text instead of a cramped rotated axis. Every bar carries its own
 * value, which is also what discharges the palette's light-mode contrast warning.
 */
export function BarChart({
  title,
  categories,
  values,
  locale,
}: {
  title: Bilingual;
  categories: string[];
  values: number[];
  locale: string;
}) {
  const key = locale as Locale;
  const label = title[key] || title.en;
  const max = Math.max(...values, 0) || 1;

  return (
    <figure
      role="img"
      aria-label={label}
      className="rounded-lg border border-border bg-surface p-5"
    >
      <figcaption className="mb-4 text-sm font-medium">{label}</figcaption>

      <div className="flex flex-col gap-2.5">
        {categories.map((category, index) => (
          <div key={`${category}-${index}`} className="grid grid-cols-[10rem_1fr_auto] items-center gap-3">
            <span className="truncate text-xs text-muted" title={category}>
              {category}
            </span>
            <div className="h-3.5 w-full">
              <div
                className="h-full rounded-e-[4px] bg-[var(--series-1)]"
                style={{ width: `${Math.max((values[index] / max) * 100, 1.5)}%` }}
              />
            </div>
            <span className="text-xs tabular-nums text-foreground">
              {formatNumber(values[index], locale)}
            </span>
          </div>
        ))}
      </div>
    </figure>
  );
}
