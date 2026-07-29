import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { NextIntlClientProvider } from "next-intl";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import messages from "../../messages/en.json";
import { EntityCard } from "../../src/components/review/entity-card";
import type { EntityOut } from "../../src/lib/api/types";

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "bypass" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const ENTITY: EntityOut = {
  id: "e1", kind: "table", schema_name: "public", name: "leave_requests",
  status: "pending", confidence: 0.86, row_count_approx: 4, version: 1,
  structural: {},
  description_ai: {
    summary: { fa: "درخواست‌های مرخصی کارکنان", en: "Employee leave requests" },
    grain: "one row per leave request",
    common_questions: ["افرادی که این ماه مرخصی گرفتند"],
  },
  description_human: null,
  approved_by: null,
  approved_at: null,
  fields: [
    {
      id: "f1", name: "id", data_type: "INTEGER", nullable: false, is_pk: true, ordinal: 0,
      meaning_ai: { fa: "شناسه", en: "Identifier" }, meaning_human: null,
      enum_map: null, unit: null, pii_class: "none", confidence: 0.99,
    },
    {
      id: "f2", name: "status", data_type: "SMALLINT", nullable: false, is_pk: false, ordinal: 1,
      meaning_ai: { fa: "وضعیت", en: "Status" }, meaning_human: null,
      enum_map: {
        "1": { fa: "در انتظار", en: "pending" },
        "2": { fa: "تایید شده", en: "approved" },
      },
      unit: null, pii_class: "none", confidence: 0.95,
    },
    {
      id: "f3", name: "national_id", data_type: "CHAR(10)", nullable: true, is_pk: false,
      ordinal: 2, meaning_ai: { fa: "کد ملی", en: "National ID" }, meaning_human: null,
      enum_map: null, unit: null, pii_class: "high", confidence: 0.9,
    },
  ],
};

function renderCard(entity: EntityOut = ENTITY) {
  const onChanged = vi.fn();
  const onApproved = vi.fn();
  render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <EntityCard entity={entity} locale="en" onChanged={onChanged} onApproved={onApproved} />
    </NextIntlClientProvider>,
  );
  return { onChanged, onApproved };
}

describe("EntityCard", () => {
  it("shows the AI summary in the active locale", () => {
    renderCard();
    expect(screen.getByText("Employee leave requests")).toBeInTheDocument();
  });

  it("keeps the AI original visible after a human edit", () => {
    renderCard({
      ...ENTITY,
      description_human: { summary: { fa: "دست‌نویس", en: "My own wording" } },
    });
    // The human text is the answer; the AI text stays as the audit trail.
    expect(screen.getByText("My own wording")).toBeInTheDocument();
    expect(screen.getByText("Employee leave requests")).toBeInTheDocument();
  });

  it("saves an edited summary as description_human", async () => {
    let body: unknown;
    server.use(
      http.patch("*/api/entities/e1", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ ...ENTITY, description_human: body.description_human });
      }),
    );
    const { onChanged } = renderCard();

    await userEvent.click(screen.getByRole("button", { name: /edit summary/i }));
    const box = screen.getByRole("textbox", { name: /summary/i });
    await userEvent.clear(box);
    await userEvent.type(box, "Corrected wording");
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await vi.waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect(body).toMatchObject({
      description_human: { summary: { en: "Corrected wording" } },
    });
  });

  it("preserves the other locale's text when saving an edit", async () => {
    let body: { description_human?: { summary?: { fa?: string } } } | undefined;
    server.use(
      http.patch("*/api/entities/e1", async ({ request }) => {
        body = (await request.json()) as typeof body;
        return HttpResponse.json(ENTITY);
      }),
    );
    renderCard();

    await userEvent.click(screen.getByRole("button", { name: /edit summary/i }));
    const box = screen.getByRole("textbox", { name: /summary/i });
    await userEvent.clear(box);
    await userEvent.type(box, "English only edit");
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    // Editing English must not blank the Persian summary.
    await vi.waitFor(() => expect(body?.description_human?.summary?.fa).toBeTruthy());
  });

  it("renders the enum decoding for a coded column as editable values", () => {
    renderCard();
    // The decoding is the reviewer's main correction target, so it is an input,
    // not static text: status = 2 meaning "approved" must be fixable in place.
    expect(screen.getByLabelText("status 2")).toHaveValue("approved");
    expect(screen.getByLabelText("status 1")).toHaveValue("pending");
  });

  it("marks a high-PII column so the reviewer knows it was never sampled", () => {
    renderCard();
    expect(screen.getByRole("row", { name: /national_id/ })).toHaveTextContent(/high/i);
  });

  it("approves the entity and reports it upward", async () => {
    server.use(
      http.post("*/api/entities/e1/approve", () =>
        HttpResponse.json({ ...ENTITY, status: "approved" }),
      ),
    );
    const { onApproved } = renderCard();

    await userEvent.click(screen.getByRole("button", { name: /^approve$/i }));
    await vi.waitFor(() => expect(onApproved).toHaveBeenCalled());
  });

  it("shows a diff prompt for a stale entity", () => {
    renderCard({ ...ENTITY, status: "stale" });
    expect(screen.getByText(/changed since it was approved/i)).toBeInTheDocument();
  });

  it("offers a retry rather than an approve for a failed description", () => {
    renderCard({ ...ENTITY, status: "describe_failed", description_ai: null });
    // Approving a description that does not exist would be meaningless.
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^approve$/i })).not.toBeInTheDocument();
  });
});
