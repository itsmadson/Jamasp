"use client";

import { useTranslations } from "next-intl";

import { formatDate, formatNumber } from "@/lib/format";
import type { AskResponse } from "@/lib/api/query";

type Column = AskResponse["columns"][number];

function renderCell(value: unknown, column: Column, locale: string): string {
  if (value === null || value === undefined) return "—";
  if (column.type === "number") return formatNumber(Number(value), locale);
  if (column.type === "temporal") return formatDate(String(value), locale);
  if (column.type === "boolean") return String(value);
  return String(value);
}

export function ResultTable({
  columns,
  rows,
  locale,
}: {
  columns: Column[];
  rows: Record<string, unknown>[];
  locale: string;
}) {
  const t = useTranslations("ask");

  if (rows.length === 0) {
    // An empty answer is an answer: the query ran and matched nothing.
    return (
      <p className="rounded-lg border border-dashed border-border px-6 py-10 text-center text-sm text-muted">
        {t("noRows")}
      </p>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-border bg-foreground/[0.03] text-xs uppercase tracking-wide text-muted">
            {columns.map((column) => (
              <th key={column.name} className="px-3 py-2 text-start font-medium">
                <span className="identifier">{column.name}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index} className="border-b border-border/50">
              {columns.map((column) => (
                <td
                  key={column.name}
                  className={
                    column.type === "number" ? "px-3 py-2 text-end tabular-nums" : "px-3 py-2"
                  }
                >
                  {renderCell(row[column.name], column, locale)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
