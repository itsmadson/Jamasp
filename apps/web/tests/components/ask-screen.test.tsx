import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { NextIntlClientProvider } from "next-intl";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import messages from "../../messages/en.json";
import faMessages from "../../messages/fa.json";
import { AskScreen } from "../../src/components/query/ask-screen";

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "bypass" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const ANSWER = {
  id: "q1",
  question: "چه کسانی مرخصی تاییدشده دارند؟",
  sql: "SELECT e.full_name FROM leave_requests l JOIN employees e ON e.id = l.emp_id WHERE l.status = 2",
  explanation: {
    fa: "کارکنانی که مرخصی تاییدشده دارند",
    en: "Employees with approved leave",
  },
  tables_used: ["leave_requests", "employees"],
  assumptions: ["«این ماه» به ماه میلادی جاری تعبیر شد"],
  columns: [
    { name: "full_name", type: "text" },
    { name: "days", type: "number" },
  ],
  rows: [
    { full_name: "علی رضایی", days: 1234 },
    { full_name: "مریم کریمی", days: 7 },
  ],
  row_count: 2,
  duration_ms: 45,
};

function renderAsk(locale: "en" | "fa" = "en") {
  render(
    <NextIntlClientProvider locale={locale} messages={locale === "fa" ? faMessages : messages}>
      <AskScreen locale={locale} sourceId="s1" />
    </NextIntlClientProvider>,
  );
}

async function submit(question: string, locale: "en" | "fa" = "en") {
  // Labels are translated, so the query has to follow the locale under test.
  const catalog = locale === "fa" ? faMessages : messages;
  await userEvent.type(
    screen.getByRole("textbox", { name: catalog.ask.question }),
    question,
  );
  await userEvent.click(screen.getByRole("button", { name: catalog.ask.ask }));
}

describe("AskScreen", () => {
  it("renders returned rows in a table", async () => {
    server.use(http.post("*/api/sources/s1/query", () => HttpResponse.json(ANSWER)));
    renderAsk();
    await submit("who has approved leave");

    expect(await screen.findByText("علی رضایی")).toBeInTheDocument();
    expect(screen.getByText("مریم کریمی")).toBeInTheDocument();
  });

  it("shows the explanation, because the reader may not read SQL", async () => {
    server.use(http.post("*/api/sources/s1/query", () => HttpResponse.json(ANSWER)));
    renderAsk();
    await submit("who has approved leave");

    expect(await screen.findByText("Employees with approved leave")).toBeInTheDocument();
  });

  it("shows the generated SQL for anyone who does read it", async () => {
    server.use(http.post("*/api/sources/s1/query", () => HttpResponse.json(ANSWER)));
    renderAsk();
    await submit("who has approved leave");

    expect(await screen.findByText(/WHERE l.status = 2/)).toBeInTheDocument();
  });

  it("surfaces the model's stated assumptions", async () => {
    server.use(http.post("*/api/sources/s1/query", () => HttpResponse.json(ANSWER)));
    renderAsk();
    await submit("leave this month");

    // An unstated date-range reading is how a plausible report ends up wrong.
    expect(await screen.findByText(/این ماه/)).toBeInTheDocument();
  });

  it("formats numeric cells with Persian digits in the Persian locale", async () => {
    server.use(http.post("*/api/sources/s1/query", () => HttpResponse.json(ANSWER)));
    renderAsk("fa");
    await submit("مرخصی", "fa");

    expect(await screen.findByText("۱٬۲۳۴")).toBeInTheDocument();
  });

  it("explains a refusal instead of showing a bare error", async () => {
    server.use(
      http.post("*/api/sources/s1/query", () =>
        HttpResponse.json(
          {
            detail: {
              status: "no_match",
              message: "No approved table matches this question.",
              sql: null,
            },
          },
          { status: 422 },
        ),
      ),
    );
    renderAsk();
    await submit("stock price");

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/no approved table/i);
  });

  it("shows the rejected SQL when a query was refused as unsafe", async () => {
    server.use(
      http.post("*/api/sources/s1/query", () =>
        HttpResponse.json(
          {
            detail: {
              status: "unsafe",
              message: "query references tables that are not approved: secrets",
              sql: "SELECT * FROM secrets",
            },
          },
          { status: 422 },
        ),
      ),
    );
    renderAsk();
    await submit("secrets");

    expect(await screen.findByText(/SELECT \* FROM secrets/)).toBeInTheDocument();
  });

  it("reports an empty result as an answer rather than a failure", async () => {
    server.use(
      http.post("*/api/sources/s1/query", () =>
        HttpResponse.json({ ...ANSWER, rows: [], row_count: 0, columns: [] }),
      ),
    );
    renderAsk();
    await submit("leave in 1990");

    expect(await screen.findByText(/no rows/i)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
