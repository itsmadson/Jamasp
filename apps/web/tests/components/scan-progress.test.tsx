import { render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { act } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../messages/en.json";
import { ScanProgress } from "../../src/components/sources/scan-progress";

class MockEventSource {
  static instances: MockEventSource[] = [];
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: ((event: unknown) => void) | null = null;
  closed = false;

  constructor(readonly url: string) {
    MockEventSource.instances.push(this);
  }

  emit(payload: object) {
    act(() => {
      this.onmessage?.({ data: JSON.stringify(payload) });
    });
  }

  fail() {
    act(() => {
      this.onerror?.(new Event("error"));
    });
  }

  close() {
    this.closed = true;
  }
}

beforeEach(() => {
  MockEventSource.instances = [];
  vi.stubGlobal("EventSource", MockEventSource);
});
afterEach(() => vi.unstubAllGlobals());

function renderProgress() {
  render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <ScanProgress scanId="scan-1" />
    </NextIntlClientProvider>,
  );
  return MockEventSource.instances[0];
}

describe("ScanProgress", () => {
  it("renders the current stage as events arrive", async () => {
    const source = renderProgress();
    source.emit({ stage: "introspect", current: 0, total: 1, message: "public.employees" });

    // The translated stage label and the raw server message are both shown.
    expect(await screen.findByText("Reading schema")).toBeInTheDocument();
    expect(screen.getByText("public.employees")).toBeInTheDocument();
  });

  it("shows per-entity progress during the describe stage", async () => {
    const source = renderProgress();
    source.emit({ stage: "describe", current: 3, total: 12, message: "leave_requests" });

    expect(await screen.findByText(/leave_requests/)).toBeInTheDocument();
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuenow", "3");
    expect(bar).toHaveAttribute("aria-valuemax", "12");
  });

  it("closes the connection when the terminal event arrives", async () => {
    const source = renderProgress();
    source.emit({ stage: "done", status: "succeeded" });
    await waitFor(() => expect(source.closed).toBe(true));
  });

  it("surfaces a partial scan distinctly from a successful one", async () => {
    const source = renderProgress();
    source.emit({ stage: "done", status: "partial" });

    // A partial scan means some tables have no description. Reporting it as a
    // plain success would hide work the reviewer still has to chase.
    expect(await screen.findByText(/could not be described/i)).toBeInTheDocument();
    expect(screen.queryByText("Scan finished.")).not.toBeInTheDocument();
  });

  it("reports a dropped connection instead of hanging silently", async () => {
    const source = renderProgress();
    source.fail();
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
