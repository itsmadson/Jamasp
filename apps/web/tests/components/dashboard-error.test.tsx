import { render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it, vi } from "vitest";

import messages from "../../messages/en.json";

const getOverview = vi.fn();
vi.mock("@/lib/api/overview", () => ({ getOverview: () => getOverview() }));

const { Dashboard } = await import("../../src/components/dashboard/dashboard");

/**
 * Its own file on purpose. Sharing one with the success cases made the runner
 * report the rejection as an unhandled error and fail the run, even though the
 * component catches it — the same pattern passes cleanly in isolation.
 */
describe("Dashboard, when the overview cannot be loaded", () => {
  it("says so instead of showing an empty page", async () => {
    getOverview.mockImplementation(async () => {
      throw new Error("network");
    });

    render(
      <NextIntlClientProvider locale="en" messages={messages}>
        <Dashboard locale="en" />
      </NextIntlClientProvider>,
    );

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(/could not load/i),
    );
  });
});
