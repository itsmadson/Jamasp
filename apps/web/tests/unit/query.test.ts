import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import { ask, QueryRefused } from "../../src/lib/api/query";

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const ANSWER = {
  id: "q1",
  question: "چه کسانی مرخصی دارند؟",
  sql: "SELECT 1",
  explanation: { fa: "توضیح", en: "Explanation" },
  tables_used: ["leave_requests"],
  assumptions: [],
  columns: [{ name: "n", type: "number" }],
  rows: [{ n: 4 }],
  row_count: 1,
  duration_ms: 12,
};

describe("ask", () => {
  it("returns the answer on success", async () => {
    server.use(http.post("*/api/sources/s1/query", () => HttpResponse.json(ANSWER)));
    const result = await ask("s1", "چه کسانی مرخصی دارند؟", "fa");
    expect(result.rows).toEqual([{ n: 4 }]);
    expect(result.explanation.fa).toBe("توضیح");
  });

  it("surfaces a no_match refusal as structure, not a generic failure", async () => {
    // FastAPI serialises a dict detail as an object; losing that shape would
    // reduce a considered refusal to an unexplained error.
    server.use(
      http.post("*/api/sources/s1/query", () =>
        HttpResponse.json(
          {
            detail: {
              status: "no_match",
              message: "No approved table matches this question.",
              sql: null,
            },
          },
          { status: 422 },
        ),
      ),
    );

    await expect(ask("s1", "قیمت سهام؟", "fa")).rejects.toMatchObject({
      name: "QueryRefused",
      status: "no_match",
    });
  });

  it("keeps the rejected SQL so a human can inspect what was refused", async () => {
    server.use(
      http.post("*/api/sources/s1/query", () =>
        HttpResponse.json(
          {
            detail: {
              status: "unsafe",
              message: "query references tables that are not approved: secrets",
              sql: "SELECT * FROM secrets",
            },
          },
          { status: 422 },
        ),
      ),
    );

    const caught = await ask("s1", "…", "fa").catch((error) => error);
    expect(caught).toBeInstanceOf(QueryRefused);
    expect(caught.sql).toBe("SELECT * FROM secrets");
    expect(caught.status).toBe("unsafe");
  });

  it("still throws a plain error for transport failures", async () => {
    server.use(
      http.post("*/api/sources/s1/query", () => new HttpResponse(null, { status: 500 })),
    );
    await expect(ask("s1", "…", "fa")).rejects.not.toBeInstanceOf(QueryRefused);
  });
});
