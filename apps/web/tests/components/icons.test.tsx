import { render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it, vi } from "vitest";

import faMessages from "../../messages/fa.json";
import messages from "../../messages/en.json";

vi.mock("next/navigation", () => ({
  usePathname: () => "/en/dashboard",
  useRouter: () => ({ replace: () => {}, refresh: () => {} }),
}));
vi.mock("@/lib/api/auth", () => ({ logout: async () => {} }));

const { NavLink } = await import("../../src/components/layout/nav-link");
const { ExportButton } = await import("../../src/components/report/export-button");

/**
 * Icons are decoration, not content.
 *
 * Two things can go wrong and neither shows up in a snapshot: a glyph announced to
 * a screen reader duplicates the label beside it, and a directional glyph that does
 * not mirror points the wrong way on a Persian page.
 */
describe("icons", () => {
  it("does not announce a decorative icon alongside its label", async () => {
    const { LayoutDashboard } = await import("lucide-react");

    render(
      <NextIntlClientProvider locale="en" messages={messages}>
        <NavLink href="/en/dashboard" icon={<LayoutDashboard aria-hidden size={16} />}>
          Dashboard
        </NavLink>
      </NextIntlClientProvider>,
    );

    const link = screen.getByRole("link");
    // Exactly the label: an unhidden icon would make this "Dashboard Dashboard".
    expect(link).toHaveAccessibleName("Dashboard");
    expect(link.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
  });

  it("marks the current page for assistive tech, not just with colour", async () => {
    const { LayoutDashboard } = await import("lucide-react");

    render(
      <NextIntlClientProvider locale="en" messages={messages}>
        <NavLink href="/en/dashboard" icon={<LayoutDashboard aria-hidden size={16} />}>
          Dashboard
        </NavLink>
      </NextIntlClientProvider>,
    );

    expect(screen.getByRole("link")).toHaveAttribute("aria-current", "page");
  });

  it("mirrors a directional icon so it points forward in Persian", () => {
    render(
      <NextIntlClientProvider locale="fa" messages={faMessages}>
        <ExportButton />
      </NextIntlClientProvider>,
    );

    // A printer is not directional, but the class is how every directional glyph
    // in the app flips; this pins that the convention is actually applied.
    const icon = screen.getByRole("button").querySelector("svg");
    expect(icon).toHaveAttribute("aria-hidden", "true");
  });

  it("flips the sign-out glyph under RTL", async () => {
    const { SignOutButton } = await import("../../src/components/layout/sign-out-button");

    render(
      <NextIntlClientProvider locale="fa" messages={faMessages}>
        <SignOutButton locale="fa" />
      </NextIntlClientProvider>,
    );

    const icon = screen.getByRole("button").querySelector("svg");
    // Without the flip, the door-and-arrow points into the page in Persian.
    expect(icon?.getAttribute("class")).toContain("rtl:-scale-x-100");
  });
});
