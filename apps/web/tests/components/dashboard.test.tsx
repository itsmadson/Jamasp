import { render, screen, within } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../messages/en.json";
import faMessages from "../../messages/fa.json";

const getOverview = vi.fn();
vi.mock("@/lib/api/overview", () => ({ getOverview: () => getOverview() }));

const { Dashboard } = await import("../../src/components/dashboard/dashboard");

function source(overrides: Record<string, unknown> = {}) {
  return {
    id: "s1",
    name: "warehouse",
    kind: "postgres",
    status: "ready",
    last_scan_at: "2026-07-01T10:00:00Z",
    last_scan_status: "succeeded",
    entities_total: 10,
    entities_approved: 10,
    entities_pending: 0,
    reports: 2,
    questions: 5,
    next_step: "ready",
    ...overrides,
  };
}

function renderDashboard(
  body: Record<string, unknown>,
  locale: "en" | "fa" = "en",
) {
  getOverview.mockResolvedValue({
    sources: [],
    recent: [],
    totals: {
      sources: 0,
      entities: 0,
      approved: 0,
      pending: 0,
      reports: 0,
      questions: 0,
    },
    ...body,
  });
  render(
    <NextIntlClientProvider
      locale={locale}
      messages={locale === "fa" ? faMessages : messages}
    >
      <Dashboard locale={locale} />
    </NextIntlClientProvider>,
  );
}

describe("Dashboard", () => {
  beforeEach(() => getOverview.mockReset());

  it("tells a brand new install to connect something", async () => {
    renderDashboard({});
    // Zeroed stat tiles would be a worse first impression than a clear invitation.
    expect(
      await screen.findByText(/connect your first database/i),
    ).toBeInTheDocument();
  });

  it("surfaces the one action a source is waiting for", async () => {
    renderDashboard({
      sources: [
        source({
          next_step: "review",
          entities_pending: 4,
          entities_approved: 6,
        }),
      ],
      totals: {
        sources: 1,
        entities: 10,
        approved: 6,
        pending: 4,
        reports: 0,
        questions: 0,
      },
    });

    // Twice: the attention list is a subset of all sources, so both show it.
    const actions = await screen.findAllByRole("link", {
      name: /review tables/i,
    });
    expect(actions[0]).toHaveAttribute("href", "/en/sources/s1/review");
  });

  it("sends a scanned and approved source to the workspace, preselected", async () => {
    renderDashboard({ sources: [source()] });

    const action = (
      await screen.findAllByRole("link", { name: /open workspace/i })
    )[0];
    // Carrying the source across means the user does not re-pick what they clicked.
    expect(action).toHaveAttribute("href", "/en/workspace?source=s1");
  });

  it("does not ask for another scan while one is running", async () => {
    renderDashboard({
      sources: [source({ next_step: "scanning", status: "scanning" })],
    });

    expect(
      await screen.findAllByRole("link", { name: /scanning/i }),
    ).not.toHaveLength(0);
    expect(
      screen.queryByRole("link", { name: /run a scan/i }),
    ).not.toBeInTheDocument();
  });

  it("lists a source needing review under attention as well as under all sources", async () => {
    renderDashboard({
      sources: [source({ next_step: "review", entities_pending: 3 })],
    });

    // By role, because the page subtitle mentions attention too.
    await screen.findByRole("heading", { name: /needs your attention/i });
    // Once in each section: the point of the attention list is that it is a subset.
    expect(screen.getAllByRole("link", { name: "warehouse" })).toHaveLength(2);
  });

  it("counts work awaiting review in the tile and marks it", async () => {
    renderDashboard({
      sources: [source({ next_step: "review", entities_pending: 4 })],
      totals: {
        sources: 1,
        entities: 10,
        approved: 6,
        pending: 4,
        reports: 0,
        questions: 0,
      },
    });

    // Exact, so this matches the tile's label and not the row's "4 awaiting review".
    const tile = (await screen.findByText("Awaiting review")).closest("div");
    expect(within(tile as HTMLElement).getByText("4")).toBeInTheDocument();
  });

  it("links a recent report but not a recent question", async () => {
    renderDashboard({
      sources: [source()],
      recent: [
        {
          kind: "report",
          id: "r1",
          data_source_id: "s1",
          title: "Users by role",
          status: "succeeded",
          created_at: "2026-07-02T10:00:00Z",
        },
        {
          kind: "question",
          id: "q1",
          data_source_id: "s1",
          title: "how many users?",
          status: "succeeded",
          created_at: "2026-07-01T10:00:00Z",
        },
      ],
    });

    expect(
      await screen.findByRole("link", { name: "Users by role" }),
    ).toHaveAttribute("href", "/en/reports/r1");
    // A question has nowhere of its own to open.
    expect(
      screen.queryByRole("link", { name: /how many users/i }),
    ).not.toBeInTheDocument();
  });

  it("renders in Persian without falling back to English labels", async () => {
    renderDashboard(
      { sources: [source({ next_step: "scan", entities_total: 0 })] },
      "fa",
    );

    expect(await screen.findByText("میزکار")).toBeInTheDocument();
    expect(
      screen.getAllByRole("link", { name: "اجرای پویش" }),
    ).not.toHaveLength(0);
  });
});
