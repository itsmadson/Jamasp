"use client";

import { useTranslations } from "next-intl";

import { ResultTable } from "@/components/query/result-table";
import type { Locale } from "@/i18n/routing";
import type { Bilingual } from "@/lib/api/types";

import { BarChart } from "./bar-chart";
import { KpiTile, aggregate, type Aggregate } from "./kpi-tile";
import { LineChart } from "./line-chart";

export interface ReportBlock {
  type: "kpi" | "bar" | "line" | "table";
  title: Bilingual;
  label?: Bilingual;
  x?: string | null;
  y?: string | null;
  series?: string | null;
  column?: string | null;
  aggregate?: Aggregate | null;
  unit?: string | null;
  columns?: string[] | null;
}

export interface ReportSpec {
  schema_version: string;
  title: Bilingual;
  summary: Bilingual;
  blocks: ReportBlock[];
}

type Column = { name: string; type: "number" | "text" | "temporal" | "boolean" };

export function ReportView({
  spec,
  columns,
  rows,
  locale,
}: {
  spec: ReportSpec;
  columns: Column[];
  rows: Record<string, unknown>[];
  locale: string;
}) {
  const t = useTranslations("report");
  const key = locale as Locale;
  const names = new Set(columns.map((column) => column.name));

  function renderBlock(block: ReportBlock, index: number) {
    // Data can move under a saved report. A block whose column is gone is skipped
    // rather than rendered broken — the rest of the report is still true.
    if (block.type === "kpi") {
      if (!block.column || !names.has(block.column)) return null;
      return (
        <KpiTile
          key={index}
          title={block.title}
          label={block.label ?? block.title}
          value={aggregate(rows, block.column, block.aggregate ?? "first")}
          unit={block.unit ?? null}
          locale={locale}
        />
      );
    }

    if (block.type === "bar" || block.type === "line") {
      const { x, y } = block;
      if (!x || !y || !names.has(x) || !names.has(y)) return null;
      const labels = rows.map((row) => String(row[x] ?? ""));
      const values = rows.map((row) => Number(row[y]) || 0);
      if (values.length === 0) return null;

      return block.type === "bar" ? (
        <BarChart
          key={index}
          title={block.title}
          categories={labels}
          values={values}
          locale={locale}
        />
      ) : (
        <LineChart
          key={index}
          title={block.title}
          labels={labels}
          values={values}
          locale={locale}
        />
      );
    }

    const wanted = (block.columns ?? []).filter((name) => names.has(name));
    const tableColumns = wanted.length
      ? columns.filter((column) => wanted.includes(column.name))
      : columns;

    return (
      <div key={index} className="flex flex-col gap-2">
        <h3 className="text-sm font-medium">{block.title[key] || block.title.en}</h3>
        <ResultTable columns={tableColumns} rows={rows} locale={locale} />
      </div>
    );
  }

  const rendered = spec.blocks.map(renderBlock).filter(Boolean);
  const hasChart = spec.blocks.some((block) => block.type === "bar" || block.type === "line");

  return (
    <article className="flex flex-col gap-6">
      <header>
        <h1 className="text-2xl font-bold tracking-tight">
          {spec.title[key] || spec.title.en}
        </h1>
        {spec.summary[key] || spec.summary.en ? (
          <p className="mt-1 text-sm text-muted">{spec.summary[key] || spec.summary.en}</p>
        ) : null}
      </header>

      {rows.length === 0 ? (
        <p className="rounded-lg border border-dashed border-border px-6 py-12 text-center text-sm text-muted">
          {t("noRows")}
        </p>
      ) : (
        <>
          <div className="flex flex-col gap-5">{rendered}</div>

          {/* Every chart is backed by the numbers themselves. Required by the
              palette's light-mode contrast result, and right regardless. */}
          {hasChart ? (
            <details className="rounded-lg border border-border">
              <summary className="cursor-pointer px-4 py-2 text-sm font-medium">
                {t("dataTable")}
              </summary>
              <div className="px-4 pb-4">
                <ResultTable columns={columns} rows={rows} locale={locale} />
              </div>
            </details>
          ) : null}
        </>
      )}
    </article>
  );
}
