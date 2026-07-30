"use client";

import { useTranslations } from "next-intl";

import { ResultTable } from "@/components/query/result-table";
import type { Locale } from "@/i18n/routing";
import type { ReportDataset } from "@/lib/api/reports";
import type { Bilingual } from "@/lib/api/types";

import { BarChart } from "./bar-chart";
import { KpiTile, aggregate, type Aggregate } from "./kpi-tile";
import { LineChart } from "./line-chart";
import { PieChart } from "./pie-chart";
import { RadarChart } from "./radar-chart";

export interface ReportBlock {
  type: "kpi" | "bar" | "line" | "area" | "pie" | "donut" | "radar" | "table";
  title: Bilingual;
  /** What this block says about its own numbers. */
  narrative?: Bilingual;
  /** Which panel this block draws from. Blocks never mix panels. */
  dataset?: string;
  /** How many of the three grid columns this block occupies. */
  span?: number;
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
  datasets?: { key: string; question: string | null }[];
  /** Observations across panels — the part a reader quotes. */
  findings?: Bilingual[];
}

const SPAN_CLASS: Record<number, string> = {
  1: "md:col-span-1",
  2: "md:col-span-2",
  3: "md:col-span-3",
};

export function ReportView({
  spec,
  datasets,
  locale,
}: {
  spec: ReportSpec;
  datasets: ReportDataset[];
  locale: string;
}) {
  const t = useTranslations("report");
  const key = locale as Locale;

  const byKey = new Map(datasets.map((dataset) => [dataset.key, dataset]));
  const only = datasets.length === 1 ? datasets[0] : null;

  function panelFor(block: ReportBlock): ReportDataset | null {
    // With one panel an unnamed block is unambiguous. With several, a block naming
    // no panel is not drawn: guessing would plot one panel's rows against another's
    // axes, which is exactly what a single merged query used to do.
    if (block.dataset) return byKey.get(block.dataset) ?? null;
    return only;
  }

  function say(block: ReportBlock, panel: ReportDataset): string {
    // The block's own words if the designer wrote them, otherwise the panel's
    // computed facts. A chart with nothing next to it makes the reader do the
    // reading.
    return (
      block.narrative?.[key] ||
      block.narrative?.en ||
      panel.narrative?.[key] ||
      panel.narrative?.en ||
      ""
    );
  }

  function renderBlock(block: ReportBlock, index: number) {
    const panel = panelFor(block);
    if (!panel) return null;

    const { rows, columns } = panel;
    const names = new Set(columns.map((column) => column.name));
    const span = SPAN_CLASS[block.span ?? 2] ?? SPAN_CLASS[2];

    // Data can move under a saved report. A block whose column is gone is skipped
    // rather than rendered broken — the rest of the report is still true.
    if (block.type === "kpi") {
      if (!block.column || !names.has(block.column)) return null;
      return (
        <div key={index} className="flex flex-col gap-1.5">
          <KpiTile
            title={block.title}
            label={block.label ?? block.title}
            value={aggregate(rows, block.column, block.aggregate ?? "first")}
            unit={block.unit ?? null}
            locale={locale}
          />
          {say(block, panel) ? (
            <p className="px-1 text-xs leading-relaxed text-muted">
              {say(block, panel)}
            </p>
          ) : null}
        </div>
      );
    }

    if (block.type === "table") {
      const wanted = (block.columns ?? []).filter((name) => names.has(name));
      const tableColumns = wanted.length
        ? columns.filter((column) => wanted.includes(column.name))
        : columns;
      return (
        <section key={index} className={`${span} flex flex-col gap-2`}>
          <h3 className="text-sm font-medium">
            {block.title[key] || block.title.en}
          </h3>
          {say(block, panel) ? (
            <p className="text-xs leading-relaxed text-muted">
              {say(block, panel)}
            </p>
          ) : null}
          <ResultTable columns={tableColumns} rows={rows} locale={locale} />
        </section>
      );
    }

    const { x, y } = block;
    if (!x || !y || !names.has(x) || !names.has(y)) return null;
    const labels = rows.map((row) => String(row[x] ?? ""));
    const values = rows.map((row) => Number(row[y]) || 0);
    if (values.length === 0) return null;

    const chart =
      block.type === "pie" || block.type === "donut" ? (
        <PieChart
          title={block.title}
          categories={labels}
          values={values}
          locale={locale}
          donut={block.type === "donut"}
        />
      ) : block.type === "radar" ? (
        <RadarChart
          title={block.title}
          categories={labels}
          values={values}
          locale={locale}
        />
      ) : block.type === "bar" ? (
        <BarChart
          title={block.title}
          categories={labels}
          values={values}
          locale={locale}
        />
      ) : (
        <LineChart
          title={block.title}
          labels={labels}
          values={values}
          locale={locale}
          area={block.type === "area"}
        />
      );

    const words = say(block, panel);
    return (
      <div key={index} className={`${span} flex flex-col gap-2`}>
        {chart}
        {words ? (
          <p className="px-1 text-xs leading-relaxed text-muted">{words}</p>
        ) : null}
      </div>
    );
  }

  // KPIs get their own track. Left in the three-column grid, four of them wrap as
  // three-plus-one and leave a hole where the fourth column should be.
  const kpiBlocks = spec.blocks.filter((block) => block.type === "kpi");
  const bodyBlocks = spec.blocks.filter((block) => block.type !== "kpi");
  const renderedKpis = kpiBlocks.map(renderBlock).filter(Boolean);
  const rendered = bodyBlocks.map(renderBlock).filter(Boolean);
  const withRows = datasets.filter((dataset) => dataset.rows.length > 0);
  // A table block is already the numbers, so it needs no second copy below.
  const hasChart = spec.blocks.some((block) => block.type !== "table");
  const failed = datasets.filter((dataset) => dataset.error);
  const findings = (spec.findings ?? []).filter(
    (finding) => finding[key] || finding.en,
  );

  return (
    <article className="flex flex-col gap-6">
      <header>
        <h1 className="text-2xl font-bold tracking-tight">
          {spec.title[key] || spec.title.en}
        </h1>
        {spec.summary[key] || spec.summary.en ? (
          <p className="mt-1 text-sm text-muted">
            {spec.summary[key] || spec.summary.en}
          </p>
        ) : null}
      </header>

      {findings.length > 0 ? (
        <section className="rounded-lg border border-border bg-surface p-5">
          <h2 className="mb-3 text-sm font-medium">{t("findings")}</h2>
          <ul className="flex flex-col gap-2">
            {findings.map((finding, index) => (
              <li key={index} className="flex gap-2 text-sm leading-relaxed">
                <span
                  aria-hidden
                  className="mt-1.5 size-1.5 shrink-0 rounded-full bg-accent"
                />
                <span>{finding[key] || finding.en}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {withRows.length === 0 ? (
        <p className="rounded-lg border border-dashed border-border px-6 py-12 text-center text-sm text-muted">
          {t("noRows")}
        </p>
      ) : (
        <>
          {renderedKpis.length > 0 ? (
            <div
              className={`grid gap-4 ${
                renderedKpis.length % 4 === 0
                  ? "grid-cols-2 md:grid-cols-4"
                  : renderedKpis.length % 3 === 0
                    ? "grid-cols-2 md:grid-cols-3"
                    : "grid-cols-2"
              }`}
            >
              {renderedKpis}
            </div>
          ) : null}

          {/* Bento: three columns that collapse to one when narrow, each block
              claiming the width its shape actually needs. */}
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            {rendered}
          </div>

          {/* Every chart is backed by its own panel's numbers. Required by the
              palette's light-mode contrast result, and right regardless. */}
          {hasChart ? (
            <details className="rounded-lg border border-border print:hidden">
              <summary className="cursor-pointer px-4 py-2 text-sm font-medium">
                {t("dataTable")}
              </summary>
              <div className="flex flex-col gap-5 px-4 pb-4">
                {withRows.map((dataset) => (
                  <div key={dataset.key} className="flex flex-col gap-1.5">
                    <h4 className="text-xs font-medium text-muted">
                      {dataset.question || dataset.key}
                    </h4>
                    <ResultTable
                      columns={dataset.columns}
                      rows={dataset.rows}
                      locale={locale}
                    />
                    {dataset.sql ? (
                      <pre className="identifier overflow-x-auto text-[11px] text-muted">
                        {dataset.sql}
                      </pre>
                    ) : null}
                  </div>
                ))}
              </div>
            </details>
          ) : null}
        </>
      )}

      {failed.length > 0 ? (
        <ul className="flex flex-col gap-1 text-xs text-warning">
          {failed.map((dataset) => (
            <li key={dataset.key}>
              {dataset.question || dataset.key}: {dataset.error}
            </li>
          ))}
        </ul>
      ) : null}
    </article>
  );
}
