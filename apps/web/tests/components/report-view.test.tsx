import { render, screen, within } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it } from "vitest";

import faMessages from "../../messages/fa.json";
import messages from "../../messages/en.json";
import { ReportView } from "../../src/components/report/report-view";
import { aggregate } from "../../src/components/report/kpi-tile";

const COLUMNS = [
  { name: "status_label", type: "text" as const },
  { name: "request_count", type: "number" as const },
];

const ROWS = [
  { status_label: "Pending", request_count: 1 },
  { status_label: "Approved", request_count: 2 },
  { status_label: "Rejected", request_count: 1 },
];

type Col = { name: string; type: "number" | "text" | "temporal" | "boolean" };

function panel(key: string, columns: Col[] = COLUMNS, rows: Record<string, unknown>[] = ROWS) {
  return {
    key,
    question: `what about ${key}?`,
    sql: `SELECT * FROM ${key}`,
    explanation: null,
    columns,
    rows,
    row_count: rows.length,
    error: null,
    facts: {},
    narrative: { fa: "متن محاسبه‌شده برای این بخش.", en: "Computed text for this panel." },
  };
}

function renderReport(
  spec: unknown,
  locale: "en" | "fa" = "en",
  rows = ROWS,
  datasets = [panel("main", COLUMNS, rows)],
) {
  render(
    <NextIntlClientProvider locale={locale} messages={locale === "fa" ? faMessages : messages}>
      <ReportView spec={spec as never} datasets={datasets as never} locale={locale} />
    </NextIntlClientProvider>,
  );
}

const BAR_SPEC = {
  schema_version: "1.0",
  title: { fa: "مرخصی به تفکیک وضعیت", en: "Leave by status" },
  summary: { fa: "خلاصه فارسی", en: "English summary" },
  blocks: [
    {
      type: "bar",
      title: { fa: "نمودار", en: "Requests by status" },
      x: "status_label",
      y: "request_count",
      series: null,
    },
  ],
};

describe("aggregate", () => {
  it("sums a numeric column", () => {
    expect(aggregate(ROWS, "request_count", "sum")).toBe(4);
  });

  it("averages a numeric column", () => {
    expect(aggregate(ROWS, "request_count", "avg")).toBe(4 / 3);
  });

  it("takes the first value when no aggregate makes sense", () => {
    expect(aggregate(ROWS, "status_label", "first")).toBe("Pending");
  });

  it("returns null for an empty result rather than zero", () => {
    // Zero is a measurement; "no data" is not.
    expect(aggregate([], "request_count", "sum")).toBeNull();
  });
});

describe("ReportView", () => {
  it("renders the title and summary in the active locale", () => {
    renderReport(BAR_SPEC, "fa");
    expect(screen.getByText("مرخصی به تفکیک وضعیت")).toBeInTheDocument();
    expect(screen.getByText("خلاصه فارسی")).toBeInTheDocument();
  });

  it("draws a bar per category with a visible value label", () => {
    renderReport(BAR_SPEC);
    const chart = screen.getByRole("img", { name: /requests by status/i });
    // Direct labels are what makes the chart legible without relying on color.
    expect(within(chart).getByText("Pending")).toBeInTheDocument();
    expect(within(chart).getByText("Approved")).toBeInTheDocument();
    expect(within(chart).getAllByText("2")).not.toHaveLength(0);
  });

  it("exposes the underlying numbers as a table for every chart", () => {
    renderReport(BAR_SPEC);
    // The relief rule: a chart is never the only way to read the values.
    expect(screen.getByRole("table")).toBeInTheDocument();
  });

  it("renders a kpi block as a single headline number", () => {
    renderReport({
      ...BAR_SPEC,
      blocks: [
        {
          type: "kpi",
          title: { fa: "مجموع", en: "Total requests" },
          label: { fa: "مجموع", en: "Total" },
          column: "request_count",
          aggregate: "sum",
          unit: null,
        },
      ],
    });
    expect(screen.getByText("4")).toBeInTheDocument();
    expect(screen.getByText("Total requests")).toBeInTheDocument();
  });

  it("formats kpi numbers with Persian digits in the Persian locale", () => {
    renderReport(
      {
        ...BAR_SPEC,
        blocks: [
          {
            type: "kpi", title: { fa: "مجموع", en: "Total" },
            label: { fa: "مجموع", en: "Total" },
            column: "request_count", aggregate: "sum", unit: null,
          },
        ],
      },
      "fa",
    );
    expect(screen.getByText("۴")).toBeInTheDocument();
  });

  it("renders a table block", () => {
    renderReport({
      ...BAR_SPEC,
      blocks: [
        {
          type: "table",
          title: { fa: "جدول", en: "Detail" },
          columns: ["status_label", "request_count"],
        },
      ],
    });
    expect(screen.getByText("Approved")).toBeInTheDocument();
  });

  it("shows an explicit empty state instead of a blank page", () => {
    renderReport({ ...BAR_SPEC, blocks: [] }, "en", []);
    // A blank page does not tell the user whether the query ran.
    expect(screen.getByText(/no rows/i)).toBeInTheDocument();
  });

  it("draws each block from its own panel, never the pooled rows", () => {
    // The bug this covers: three panels merged into one result set, so every chart
    // plotted all of it — months, provinces and roles on one axis.
    const monthly = panel(
      "monthly",
      [
        { name: "month", type: "temporal" as const },
        { name: "total", type: "number" as const },
      ],
      [
        { month: "2026-05", total: 30 },
        { month: "2026-06", total: 48 },
      ],
    );
    const byRole = panel(
      "by_role",
      COLUMNS,
      [
        { status_label: "Admin", request_count: 1 },
        { status_label: "Trainee", request_count: 8 },
      ],
    );

    renderReport(
      {
        ...BAR_SPEC,
        blocks: [
          {
            type: "line", title: { fa: "ماهانه", en: "Monthly" }, dataset: "monthly",
            span: 3, x: "month", y: "total",
          },
          {
            type: "bar", title: { fa: "نقش", en: "By role" }, dataset: "by_role",
            span: 1, x: "status_label", y: "request_count",
          },
        ],
      },
      "en",
      ROWS,
      [monthly, byRole],
    );

    const roleChart = screen.getByRole("img", { name: /by role/i });
    expect(within(roleChart).getByText("Trainee")).toBeInTheDocument();
    // A month label inside the role chart would mean the panels were pooled again.
    expect(within(roleChart).queryByText("2026-05")).not.toBeInTheDocument();
  });

  it("drops a block that names another panel's column", () => {
    const monthly = panel(
      "monthly",
      [
        { name: "month", type: "temporal" as const },
        { name: "total", type: "number" as const },
      ],
      [{ month: "2026-05", total: 30 }],
    );

    renderReport(
      {
        ...BAR_SPEC,
        blocks: [
          {
            type: "bar", title: { fa: "الف", en: "Borrowed" }, dataset: "monthly",
            x: "status_label", y: "request_count",
          },
        ],
      },
      "en",
      ROWS,
      [monthly, panel("other")],
    );
    expect(screen.queryByRole("img", { name: /borrowed/i })).not.toBeInTheDocument();
  });

  it("will not guess a panel when a block names none and several exist", () => {
    renderReport(
      { ...BAR_SPEC, blocks: [{ ...BAR_SPEC.blocks[0], dataset: undefined }] },
      "en",
      ROWS,
      [panel("a"), panel("b")],
    );
    // Guessing risks charting the wrong panel's numbers under the right title.
    expect(screen.queryByRole("img", { name: /requests by status/i })).not.toBeInTheDocument();
  });

  it("renders a donut with its share of the whole", () => {
    renderReport({
      ...BAR_SPEC,
      blocks: [
        {
          type: "donut", title: { fa: "سهم", en: "Share" }, dataset: "main",
          span: 1, x: "status_label", y: "request_count",
        },
      ],
    });
    const chart = screen.getByRole("img", { name: /share/i });
    expect(within(chart).getByText("Approved")).toBeInTheDocument();
    // 2 of 4 — the value and the percentage both stated, never colour alone.
    expect(within(chart).getByText("50%")).toBeInTheDocument();
  });

  it("puts words next to every chart", () => {
    renderReport({
      ...BAR_SPEC,
      blocks: [
        {
          ...BAR_SPEC.blocks[0],
          dataset: "main",
          narrative: { fa: "مصاحبه‌کننده بیشترین سهم را دارد.", en: "Interviewers lead." },
        },
      ],
    });
    // A chart with nothing beside it makes the reader do the reading.
    expect(screen.getByText("Interviewers lead.")).toBeInTheDocument();
  });

  it("falls back to the panel's computed text when a block has none", () => {
    renderReport({ ...BAR_SPEC, blocks: [{ ...BAR_SPEC.blocks[0], dataset: "main" }] });
    expect(screen.getByText("Computed text for this panel.")).toBeInTheDocument();
  });

  it("renders the findings a reader would quote", () => {
    renderReport({
      ...BAR_SPEC,
      findings: [
        { fa: "سه نقش نخست ۹۳٪ کاربران را می‌سازند.", en: "The top three roles are 93% of users." },
        { fa: "رشد ماهانه مثبت است.", en: "Monthly growth is positive." },
      ],
      blocks: [{ ...BAR_SPEC.blocks[0], dataset: "main" }],
    });
    expect(screen.getByText("The top three roles are 93% of users.")).toBeInTheDocument();
    expect(screen.getByText("Monthly growth is positive.")).toBeInTheDocument();
  });

  it("renders a radar over a handful of categories", () => {
    renderReport({
      ...BAR_SPEC,
      blocks: [
        {
          type: "radar", title: { fa: "نمای نقش", en: "Role profile" }, dataset: "main",
          span: 1, x: "status_label", y: "request_count",
        },
      ],
    });
    const chart = screen.getByRole("img", { name: /role profile/i });
    // Values are stated, never left as a vertex position to estimate.
    expect(within(chart).getByText("Pending")).toBeInTheDocument();
    expect(within(chart).getAllByText("2")).not.toHaveLength(0);
  });

  it("gives kpi blocks the narrow span so the page opens with a row of numbers", () => {
    renderReport({
      ...BAR_SPEC,
      blocks: [
        {
          type: "kpi", title: { fa: "مجموع", en: "Total" }, dataset: "main", span: 1,
          label: { fa: "مجموع", en: "Total" }, column: "request_count",
          aggregate: "sum", unit: null,
        },
      ],
    });
    expect(screen.getByText("4")).toBeInTheDocument();
  });

  it("skips a chart whose column vanished from the data", () => {
    renderReport({
      ...BAR_SPEC,
      blocks: [
        { type: "bar", title: { fa: "الف", en: "Gone" }, x: "missing", y: "request_count" },
        {
          type: "kpi", title: { fa: "مجموع", en: "Total" }, label: { fa: "م", en: "T" },
          column: "request_count", aggregate: "sum", unit: null,
        },
      ],
    });
    // One stale block must not take the rest of the report down with it.
    expect(screen.queryByRole("img", { name: /gone/i })).not.toBeInTheDocument();
    expect(screen.getByText("Total")).toBeInTheDocument();
  });
});
