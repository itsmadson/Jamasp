import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it, vi } from "vitest";

import messages from "../../messages/en.json";
import { RouteTable } from "../../src/components/settings/route-table";
import type { RouteConfig } from "../../src/lib/api/settings";

const ROUTES: Record<string, RouteConfig> = {
  describe_entity: {
    provider: "openrouter",
    model: "nvidia/nemotron-3-ultra-550b-a55b:free",
    temperature: 0.2,
    fallbacks: [],
  },
  embed: { provider: "local", model: "bge-m3", temperature: 0.2, fallbacks: [] },
};

function renderTable() {
  const onSave = vi.fn();
  render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <RouteTable routes={ROUTES} providers={["openrouter", "gapgpt", "local"]} onSave={onSave} />
    </NextIntlClientProvider>,
  );
  return { onSave };
}

describe("RouteTable", () => {
  it("lists every task with its current model", () => {
    renderTable();
    expect(screen.getByLabelText(/describe_entity model/i)).toHaveValue(
      "nvidia/nemotron-3-ultra-550b-a55b:free",
    );
    expect(screen.getByLabelText(/embed model/i)).toHaveValue("bge-m3");
  });

  it("switches a task to a local model without touching any other task", async () => {
    const { onSave } = renderTable();

    const row = screen.getByRole("row", { name: /describe_entity/ });
    await userEvent.selectOptions(within(row).getByLabelText(/provider/i), "local");
    const model = within(row).getByLabelText(/model/i);
    await userEvent.clear(model);
    await userEvent.type(model, "qwen2.5:32b");
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    // Only the edited task is sent: an untouched embed route must not be rewritten.
    expect(onSave).toHaveBeenCalledWith({
      describe_entity: expect.objectContaining({ provider: "local", model: "qwen2.5:32b" }),
    });
    expect(onSave.mock.calls[0][0]).not.toHaveProperty("embed");
  });
});
