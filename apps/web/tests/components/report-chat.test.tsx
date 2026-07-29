import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { NextIntlClientProvider } from "next-intl";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import messages from "../../messages/en.json";
import { ReportChat } from "../../src/components/report/report-chat";

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "bypass" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const UPDATED = {
  id: "r1",
  data_source_id: "s1",
  title: { fa: "گزارش", en: "Report" },
  locale: "en",
  created_at: "2026-07-29T00:00:00Z",
  spec: { schema_version: "1.0", title: { fa: "گ", en: "R" }, summary: { fa: "", en: "" }, blocks: [] },
  sql: "SELECT 1",
  explanation: null,
  columns: [],
  rows: [],
  row_count: 0,
};

function renderChat() {
  const onUpdated = vi.fn();
  render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <ReportChat reportId="r1" locale="en" onUpdated={onUpdated} />
    </NextIntlClientProvider>,
  );
  return onUpdated;
}

async function send(text: string) {
  await userEvent.type(screen.getByRole("textbox", { name: /change this report/i }), text);
  await userEvent.click(screen.getByRole("button", { name: /apply/i }));
}

describe("ReportChat", () => {
  it("applies an accepted edit and hands the new report upward", async () => {
    server.use(http.post("*/api/reports/r1/chat", () => HttpResponse.json(UPDATED)));
    const onUpdated = renderChat();

    await send("make it a line chart");

    await vi.waitFor(() =>
      expect(onUpdated).toHaveBeenCalledWith(expect.objectContaining({ id: "r1" })),
    );
  });

  it("records a rejected edit instead of leaving the user guessing", async () => {
    server.use(
      http.post("*/api/reports/r1/chat", () =>
        HttpResponse.json(
          {
            detail: {
              status: "edit_rejected",
              message: "that change would leave the report with nothing to show",
            },
          },
          { status: 422 },
        ),
      ),
    );
    const onUpdated = renderChat();

    await send("delete everything");

    expect(await screen.findByText(/nothing to show/i)).toBeInTheDocument();
    // The report is unchanged, so nothing is handed upward.
    expect(onUpdated).not.toHaveBeenCalled();
  });

  it("keeps the instruction history visible across turns", async () => {
    server.use(http.post("*/api/reports/r1/chat", () => HttpResponse.json(UPDATED)));
    renderChat();

    await send("make it a bar chart");
    expect(await screen.findByText("make it a bar chart")).toBeInTheDocument();
  });

  it("clears the input so the next instruction starts clean", async () => {
    server.use(http.post("*/api/reports/r1/chat", () => HttpResponse.json(UPDATED)));
    renderChat();

    await send("show a table");
    expect(screen.getByRole("textbox", { name: /change this report/i })).toHaveValue("");
  });
});
