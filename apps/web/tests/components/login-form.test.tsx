import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { NextIntlClientProvider } from "next-intl";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import messages from "../../messages/en.json";
import { LoginForm } from "../../src/components/auth/login-form";

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "bypass" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function renderForm(onSuccess = vi.fn()) {
  render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <LoginForm onSuccess={onSuccess} />
    </NextIntlClientProvider>,
  );
  return onSuccess;
}

describe("LoginForm", () => {
  it("calls onSuccess after a successful login", async () => {
    server.use(
      http.post("*/api/auth/login", () =>
        HttpResponse.json({ id: "1", email: "a@b.c", role: "admin", locale: "fa" }),
      ),
    );
    const onSuccess = renderForm();

    await userEvent.type(screen.getByLabelText(/email/i), "admin@agah.local");
    await userEvent.type(screen.getByLabelText(/password/i), "correct-horse");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await vi.waitFor(() =>
      expect(onSuccess).toHaveBeenCalledWith(expect.objectContaining({ role: "admin" })),
    );
  });

  it("shows the server's message when credentials are rejected", async () => {
    server.use(
      http.post("*/api/auth/login", () =>
        HttpResponse.json({ detail: "invalid email or password" }, { status: 401 }),
      ),
    );
    renderForm();

    await userEvent.type(screen.getByLabelText(/email/i), "admin@agah.local");
    await userEvent.type(screen.getByLabelText(/password/i), "wrong");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("invalid email or password");
  });

  it("keeps the password masked and never echoes it outside its own input", async () => {
    server.use(
      http.post("*/api/auth/login", () =>
        HttpResponse.json({ detail: "invalid email or password" }, { status: 401 }),
      ),
    );
    renderForm();

    const password = screen.getByLabelText(/password/i);
    await userEvent.type(password, "correct-horse");
    expect(password).toHaveAttribute("type", "password");

    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
    await screen.findByRole("alert");

    // The input necessarily holds the value; nothing else may. An error message
    // that quotes the attempted password is the failure this guards against.
    const elsewhere = Array.from(document.body.querySelectorAll("*")).filter(
      (node) => node !== password && node.textContent?.includes("correct-horse"),
    );
    expect(elsewhere).toEqual([]);
  });

  it("disables the submit button while the request is in flight", async () => {
    server.use(
      http.post("*/api/auth/login", async () => {
        await new Promise((resolve) => setTimeout(resolve, 100));
        return HttpResponse.json({ id: "1", email: "a@b.c", role: "admin", locale: "fa" });
      }),
    );
    renderForm();

    await userEvent.type(screen.getByLabelText(/email/i), "admin@agah.local");
    await userEvent.type(screen.getByLabelText(/password/i), "correct-horse");
    const button = screen.getByRole("button", { name: /sign in/i });
    await userEvent.click(button);

    expect(button).toBeDisabled();
  });
});
