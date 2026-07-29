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

function renderReport(spec: unknown, locale: "en" | "fa" = "en", rows = ROWS) {
  render(
    <NextIntlClientProvider locale={locale} messages={locale === "fa" ? faMessages : messages}>
      <ReportView
        spec={spec as never}
        columns={COLUMNS}
        rows={rows}
        locale={locale}
      />
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
