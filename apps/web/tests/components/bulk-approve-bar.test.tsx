import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { NextIntlClientProvider } from "next-intl";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import messages from "../../messages/en.json";
import { BulkApproveBar } from "../../src/components/review/bulk-approve-bar";

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "bypass" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function renderBar() {
  const onApproved = vi.fn();
  render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <BulkApproveBar pendingCount={47} sourceId="s1" onApproved={onApproved} />
    </NextIntlClientProvider>,
  );
  return { onApproved };
}

describe("BulkApproveBar", () => {
  it("requires confirmation before approving in bulk", async () => {
    let called = false;
    server.use(
      http.post("*/api/sources/s1/entities/bulk-approve", () => {
        called = true;
        return HttpResponse.json({ approved_count: 40 });
      }),
    );
    renderBar();

    await userEvent.click(screen.getByRole("button", { name: /approve all/i }));
    // Bulk approval is the one action that can rubber-stamp the human gate the
    // whole product rests on, so it never fires straight off a single click.
    expect(called).toBe(false);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("states how many tables the action will affect", async () => {
    renderBar();
    await userEvent.click(screen.getByRole("button", { name: /approve all/i }));
    expect(screen.getByRole("dialog")).toHaveTextContent("47");
  });

  it("sends the chosen threshold once confirmed", async () => {
    let body: { min_confidence?: number } | undefined;
    server.use(
      http.post("*/api/sources/s1/entities/bulk-approve", async ({ request }) => {
        body = (await request.json()) as typeof body;
        return HttpResponse.json({ approved_count: 40 });
      }),
    );
    const { onApproved } = renderBar();

    await userEvent.click(screen.getByRole("button", { name: /approve all/i }));
    await userEvent.click(screen.getByRole("button", { name: /^confirm$/i }));

    await vi.waitFor(() => expect(onApproved).toHaveBeenCalled());
    expect(body?.min_confidence).toBe(0.8);
  });

  it("cancelling leaves everything untouched", async () => {
    let called = false;
    server.use(
      http.post("*/api/sources/s1/entities/bulk-approve", () => {
        called = true;
        return HttpResponse.json({ approved_count: 40 });
      }),
    );
    renderBar();

    await userEvent.click(screen.getByRole("button", { name: /approve all/i }));
    await userEvent.click(screen.getByRole("button", { name: /^cancel$/i }));

    expect(called).toBe(false);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
