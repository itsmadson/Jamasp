import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import { ApiError, apiFetch } from "../../src/lib/api/client";

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("apiFetch", () => {
  it("returns parsed JSON on success", async () => {
    server.use(http.get("*/api/sources", () => HttpResponse.json([{ name: "HR" }])));
    await expect(apiFetch("/api/sources")).resolves.toEqual([{ name: "HR" }]);
  });

  it("sends credentials so the httpOnly session cookie travels", async () => {
    let credentials: RequestCredentials | undefined;
    server.use(
      http.get("*/api/sources", ({ request }) => {
        credentials = request.credentials;
        return HttpResponse.json([]);
      }),
    );
    await apiFetch("/api/sources");
    expect(credentials).toBe("include");
  });

  it("throws ApiError carrying the backend detail message", async () => {
    server.use(
      http.post("*/api/sources", () =>
        HttpResponse.json({ detail: "admin role required" }, { status: 403 }),
      ),
    );
    await expect(apiFetch("/api/sources", { method: "POST" })).rejects.toMatchObject({
      status: 403,
      detail: "admin role required",
    });
  });

  it("reports a legible message when the response has no JSON body", async () => {
    server.use(http.get("*/api/sources", () => new HttpResponse(null, { status: 502 })));
    await expect(apiFetch("/api/sources")).rejects.toBeInstanceOf(ApiError);
  });

  it("returns undefined for 204 responses instead of failing to parse", async () => {
    server.use(http.delete("*/api/sources/1", () => new HttpResponse(null, { status: 204 })));
    await expect(apiFetch("/api/sources/1", { method: "DELETE" })).resolves.toBeUndefined();
  });
});
