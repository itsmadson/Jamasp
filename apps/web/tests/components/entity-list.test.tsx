import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it, vi } from "vitest";

import messages from "../../messages/en.json";
import { EntityList } from "../../src/components/review/entity-list";
import type { EntitySummaryOut } from "../../src/lib/api/types";

const ENTITIES: EntitySummaryOut[] = [
  {
    id: "1", kind: "table", schema_name: "public", name: "employees",
    status: "approved", confidence: 0.95, row_count_approx: 3, version: 1,
  },
  {
    id: "2", kind: "table", schema_name: "public", name: "leave_requests",
    status: "pending", confidence: 0.62, row_count_approx: 4, version: 1,
  },
  {
    id: "3", kind: "table", schema_name: "public", name: "t_mst_01",
    status: "describe_failed", confidence: null, row_count_approx: 3, version: 1,
  },
];

function renderList(overrides: Partial<React.ComponentProps<typeof EntityList>> = {}) {
  const onSelect = vi.fn();
  const onFilterChange = vi.fn();
  render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <EntityList
        locale="en"
        entities={ENTITIES}
        total={3}
        approvedCount={1}
        selectedId="2"
        onSelect={onSelect}
        onFilterChange={onFilterChange}
        {...overrides}
      />
    </NextIntlClientProvider>,
  );
  return { onSelect, onFilterChange };
}

describe("EntityList", () => {
  it("shows review progress across the whole source", () => {
    renderList();
    // The reviewer needs to know how much of a 200-table database is left.
    expect(screen.getByText("1 / 3")).toBeInTheDocument();
  });

  it("marks the selected entity for assistive technology", () => {
    renderList();
    expect(screen.getByRole("option", { name: /leave_requests/ })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  it("calls onSelect when an entity is clicked", async () => {
    const { onSelect } = renderList();
    await userEvent.click(screen.getByRole("option", { name: /employees/ }));
    expect(onSelect).toHaveBeenCalledWith("1");
  });

  it("requests a status filter when one is chosen", async () => {
    const { onFilterChange } = renderList();
    await userEvent.selectOptions(screen.getByLabelText(/status/i), "pending");
    expect(onFilterChange).toHaveBeenCalledWith(expect.objectContaining({ status: "pending" }));
  });

  it("flags a failed description distinctly from a low-confidence one", () => {
    renderList();
    const failed = screen.getByRole("option", { name: /t_mst_01/ });
    // describe_failed needs a retry; low confidence needs a read. Different actions.
    expect(failed).toHaveTextContent(/failed/i);
  });

  it("renders an em dash rather than 0% when confidence is unknown", () => {
    renderList();
    expect(screen.getByRole("option", { name: /t_mst_01/ })).toHaveTextContent("—");
  });

  it("moves selection with the arrow keys for mouse-free review", async () => {
    const { onSelect } = renderList();
    const list = screen.getByRole("listbox");
    list.focus();
    await userEvent.keyboard("{ArrowDown}");
    // Selection was on leave_requests (index 1); down moves to t_mst_01.
    expect(onSelect).toHaveBeenCalledWith("3");
  });
});
