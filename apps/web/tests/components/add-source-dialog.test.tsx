import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { NextIntlClientProvider } from "next-intl";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import messages from "../../messages/en.json";
import { AddSourceDialog } from "../../src/components/sources/add-source-dialog";

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "bypass" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function renderDialog(onCreated = vi.fn()) {
  render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <AddSourceDialog open onClose={() => {}} onCreated={onCreated} />
    </NextIntlClientProvider>,
  );
  return onCreated;
}

describe("AddSourceDialog", () => {
  it("reports a failed connection test with the driver's own message", async () => {
    server.use(
      http.post("*/api/sources/test-connection", () =>
        HttpResponse.json({
          healthy: false,
          server_version: "",
          error: "password authentication failed",
        }),
      ),
    );
    renderDialog();

    await userEvent.type(screen.getByLabelText(/name/i), "HR");
    await userEvent.type(screen.getByLabelText(/connection/i), "postgresql://x");
    await userEvent.click(screen.getByRole("button", { name: /test connection/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "password authentication failed",
    );
  });

  it("confirms a healthy connection before allowing save", async () => {
    server.use(
      http.post("*/api/sources/test-connection", () =>
        HttpResponse.json({ healthy: true, server_version: "PostgreSQL 16.2", error: null }),
      ),
    );
    renderDialog();

    await userEvent.type(screen.getByLabelText(/name/i), "HR");
    await userEvent.type(screen.getByLabelText(/connection/i), "postgresql://x");
    await userEvent.click(screen.getByRole("button", { name: /test connection/i }));

    expect(await screen.findByText(/PostgreSQL 16.2/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^save$/i })).toBeEnabled();
  });

  it("keeps save disabled until a connection has been proven", () => {
    renderDialog();
    // Registering a source that cannot be reached only produces a failed scan later.
    expect(screen.getByRole("button", { name: /^save$/i })).toBeDisabled();
  });

  it("masks the connection string input", () => {
    renderDialog();
    expect(screen.getByLabelText(/connection/i)).toHaveAttribute("type", "password");
  });

  it("invalidates a proven connection when the DSN is edited afterwards", async () => {
    server.use(
      http.post("*/api/sources/test-connection", () =>
        HttpResponse.json({ healthy: true, server_version: "PostgreSQL 16.2", error: null }),
      ),
    );
    renderDialog();

    await userEvent.type(screen.getByLabelText(/name/i), "HR");
    await userEvent.type(screen.getByLabelText(/connection/i), "postgresql://x");
    await userEvent.click(screen.getByRole("button", { name: /test connection/i }));
    await screen.findByText(/PostgreSQL 16.2/);

    await userEvent.type(screen.getByLabelText(/connection/i), "y");
    // The proof applied to the old string; saving now would store an untested DSN.
    expect(screen.getByRole("button", { name: /^save$/i })).toBeDisabled();
  });

  it("calls onCreated with the new source and never echoes the DSN elsewhere", async () => {
    server.use(
      http.post("*/api/sources/test-connection", () =>
        HttpResponse.json({ healthy: true, server_version: "PostgreSQL 16.2", error: null }),
      ),
      http.post("*/api/sources", () =>
        HttpResponse.json(
          {
            id: "s1",
            name: "HR",
            kind: "postgres",
            sampling_policy: "masked",
            status: "draft",
            created_at: "2026-07-29T00:00:00Z",
            last_scan_at: null,
          },
          { status: 201 },
        ),
      ),
    );
    const onCreated = renderDialog();

    await userEvent.type(screen.getByLabelText(/name/i), "HR");
    const dsnInput = screen.getByLabelText(/connection/i);
    await userEvent.type(dsnInput, "postgresql://tiger@db/hr");
    await userEvent.click(screen.getByRole("button", { name: /test connection/i }));
    await screen.findByText(/PostgreSQL 16.2/);
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await vi.waitFor(() =>
      expect(onCreated).toHaveBeenCalledWith(expect.objectContaining({ id: "s1" })),
    );
    const elsewhere = Array.from(document.body.querySelectorAll("*")).filter(
      (node) => node !== dsnInput && node.textContent?.includes("tiger"),
    );
    expect(elsewhere).toEqual([]);
  });
});
