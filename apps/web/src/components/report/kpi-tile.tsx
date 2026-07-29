"use client";

import { formatNumber } from "@/lib/format";
import type { Locale } from "@/i18n/routing";
import type { Bilingual } from "@/lib/api/types";

export type Aggregate = "sum" | "avg" | "min" | "max" | "count" | "first";

export function aggregate(
  rows: Record<string, unknown>[],
  column: string,
  how: Aggregate,
): number | string | null {
  // No rows means no measurement. Returning 0 would assert something false.
  if (rows.length === 0) return null;

  if (how === "count") return rows.length;
  if (how === "first") return rows[0][column] as number | string;

  const numbers = rows
    .map((row) => Number(row[column]))
    .filter((value) => Number.isFinite(value));
  if (numbers.length === 0) return rows[0][column] as number | string;

  switch (how) {
    case "sum":
      return numbers.reduce((total, value) => total + value, 0);
    case "avg":
      return numbers.reduce((total, value) => total + value, 0) / numbers.length;
    case "min":
      return Math.min(...numbers);
    case "max":
      return Math.max(...numbers);
  }
}

export function KpiTile({
  title,
  label,
  value,
  unit,
  locale,
}: {
  title: Bilingual;
  label: Bilingual;
  value: number | string | null;
  unit: string | null;
  locale: string;
}) {
  const key = locale as Locale;
  const display =
    value === null
      ? "—"
      : typeof value === "number"
        ? formatNumber(value, locale)
        : String(value);

  return (
    <figure className="rounded-lg border border-border bg-surface p-5">
      <figcaption className="text-sm text-muted">{title[key] || title.en}</figcaption>
      <p className="mt-2 text-4xl font-bold tabular-nums tracking-tight">
        {display}
        {unit ? <span className="ms-1.5 text-lg font-medium text-muted">{unit}</span> : null}
      </p>
      {label[key] && label[key] !== title[key] ? (
        <p className="mt-1 text-xs text-muted">{label[key]}</p>
      ) : null}
    </figure>
  );
}
