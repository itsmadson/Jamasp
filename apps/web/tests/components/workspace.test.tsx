import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import { beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../messages/en.json";

const listSources = vi.fn();
const ask = vi.fn();
const queryHistory = vi.fn();
const listReports = vi.fn();
const createReport = vi.fn();
const getReport = vi.fn();

class QueryRefused extends Error {
  constructor(
    readonly status: string,
    message: string,
    readonly sql: string | null = null,
  ) {
    super(message);
  }
}

vi.mock("@/lib/api/sources", () => ({ listSources: () => listSources() }));
vi.mock("@/lib/api/query", () => ({
  ask: (...args: unknown[]) => ask(...args),
  queryHistory: (...args: unknown[]) => queryHistory(...args),
  QueryRefused,
}));
vi.mock("@/lib/api/reports", () => ({
  createReport: (...args: unknown[]) => createReport(...args),
  getReport: (...args: unknown[]) => getReport(...args),
  listReports: (...args: unknown[]) => listReports(...args),
  reportEventsUrl: (id: string) => `/api/reports/${id}/events`,
}));

const { Workspace } = await import("../../src/components/workspace/workspace");

const SOURCES = [
  { id: "s1", name: "warehouse", kind: "postgres" },
  { id: "s2", name: "shop", kind: "mysql" },
];

const ANSWER = {
  sql: "SELECT count(*) FROM users",
  explanation: { fa: "شمارش کاربران", en: "Counts the users" },
  tables_used: ["public.users"],
  assumptions: [],
  columns: [{ name: "count", type: "number" as const }],
  rows: [{ count: 127 }],
  row_count: 1,
  duration_ms: 42,
};

function renderWorkspace(initialSourceId?: string) {
  render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <Workspace locale="en" initialSourceId={initialSourceId} />
    </NextIntlClientProvider>,
  );
}

describe("Workspace", () => {
  beforeEach(() => {
    for (const mock of [listSources, ask, queryHistory, listReports, createReport, getReport]) {
      mock.mockReset();
    }
    listSources.mockResolvedValue(SOURCES);
    queryHistory.mockResolvedValue([]);
    listReports.mockResolvedValue([]);
  });

  it("selects the first source when none was given", async () => {
    renderWorkspace();
    const picker = await screen.findByRole("combobox");
    expect(picker).toHaveValue("s1");
  });

  it("honours a source carried in from the dashboard", async () => {
    renderWorkspace("s2");
    await waitFor(() => expect(screen.getByRole("combobox")).toHaveValue("s2"));
  });

  it("asks against the selected source, not the first one", async () => {
    const user = userEvent.setup();
    ask.mockResolvedValue(ANSWER);
    renderWorkspace();

    await screen.findByRole("combobox");
    await user.selectOptions(screen.getByRole("combobox"), "s2");
    await user.type(screen.getByLabelText(/your question/i), "how many?");
    await user.click(screen.getByRole("button", { name: /send/i }));

    // Sending to the wrong source would answer a question about other data.
    await waitFor(() => expect(ask).toHaveBeenCalledWith("s2", "how many?", "en"));
  });

  it("shows the question, the explanation and the numbers", async () => {
    const user = userEvent.setup();
    ask.mockResolvedValue(ANSWER);
    renderWorkspace();

    await screen.findByRole("combobox");
    await user.type(screen.getByLabelText(/your question/i), "how many users?");
    await user.click(screen.getByRole("button", { name: /send/i }));

    expect(await screen.findByText("how many users?")).toBeInTheDocument();
    expect(screen.getByText("Counts the users")).toBeInTheDocument();
    expect(screen.getByRole("table")).toBeInTheDocument();
  });

  it("clears the composer once a question is sent", async () => {
    const user = userEvent.setup();
    ask.mockResolvedValue(ANSWER);
    renderWorkspace();

    await screen.findByRole("combobox");
    const input = screen.getByLabelText(/your question/i);
    await user.type(input, "how many users?");
    await user.click(screen.getByRole("button", { name: /send/i }));

    await waitFor(() => expect(input).toHaveValue(""));
  });

  it("queues a build instead of asking when the mode is report", async () => {
    const user = userEvent.setup();
    createReport.mockResolvedValue({ id: "r1", status: "queued" });
    renderWorkspace();

    await screen.findByRole("combobox");
    await user.click(screen.getByRole("button", { name: "Report" }));
    await user.type(screen.getByLabelText(/your question/i), "growth by month");
    await user.click(screen.getByRole("button", { name: /send/i }));

    await waitFor(() =>
      expect(createReport).toHaveBeenCalledWith("s1", "growth by month", "en"),
    );
    expect(ask).not.toHaveBeenCalled();
  });

  it("keeps a refusal in the thread as an answer, not a crash", async () => {
    const user = userEvent.setup();
    ask.mockRejectedValue(
      new QueryRefused("refused_unknown_table", "salaries is not approved"),
    );
    renderWorkspace();

    await screen.findByRole("combobox");
    await user.type(screen.getByLabelText(/your question/i), "salaries?");
    await user.click(screen.getByRole("button", { name: /send/i }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/not in the approved tables/i);
    expect(alert).toHaveTextContent("salaries is not approved");
    // The question stays visible so the thread reads as a conversation.
    expect(screen.getByText("salaries?")).toBeInTheDocument();
  });

  it("merges questions and reports into one history, newest first", async () => {
    queryHistory.mockResolvedValue([
      {
        id: "q1",
        question: "older question",
        locale: "en",
        sql: null,
        explanation: null,
        status: "succeeded",
        row_count: 3,
        duration_ms: 10,
        error: null,
        created_at: "2026-07-01T10:00:00Z",
      },
    ]);
    listReports.mockResolvedValue([
      {
        id: "r1",
        data_source_id: "s1",
        title: { fa: "گزارش", en: "newer report" },
        locale: "en",
        created_at: "2026-07-02T10:00:00Z",
      },
    ]);

    renderWorkspace();

    const panel = await screen.findByRole("complementary");
    // The panel renders as soon as sources load; history arrives after.
    await within(panel).findByText("newer report");
    const items = within(panel).getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("newer report");
    expect(items[1]).toHaveTextContent("older question");
  });

  it("reloads history for the newly chosen source", async () => {
    const user = userEvent.setup();
    renderWorkspace();

    await screen.findByRole("combobox");
    await waitFor(() => expect(queryHistory).toHaveBeenCalledWith("s1"));

    await user.selectOptions(screen.getByRole("combobox"), "s2");
    // Leaving the previous source's history on screen would misattribute it.
    await waitFor(() => expect(queryHistory).toHaveBeenCalledWith("s2"));
  });

  it("puts a past question back in the composer when clicked", async () => {
    const user = userEvent.setup();
    queryHistory.mockResolvedValue([
      {
        id: "q1",
        question: "how many orders?",
        locale: "en",
        sql: null,
        explanation: null,
        status: "succeeded",
        row_count: 3,
        duration_ms: 10,
        error: null,
        created_at: "2026-07-01T10:00:00Z",
      },
    ]);
    renderWorkspace();

    const panel = await screen.findByRole("complementary");
    await user.click(await within(panel).findByRole("button", { name: "how many orders?" }));

    expect(screen.getByLabelText(/your question/i)).toHaveValue("how many orders?");
  });

  it("points at the sources page when nothing is connected", async () => {
    listSources.mockResolvedValue([]);
    renderWorkspace();

    expect(await screen.findByRole("link", { name: /add a data source/i })).toHaveAttribute(
      "href",
      "/en/sources",
    );
    // Nothing to ask about, so the composer must not invite a question.
    expect(screen.getByLabelText(/your question/i)).toBeDisabled();
  });

  it("offers examples to click before anything has been asked", async () => {
    const user = userEvent.setup();
    renderWorkspace();

    await screen.findByRole("combobox");
    await user.click(screen.getByRole("button", { name: /how many records/i }));

    expect(screen.getByLabelText(/your question/i)).toHaveValue(
      "How many records are in each table?",
    );
  });
});
