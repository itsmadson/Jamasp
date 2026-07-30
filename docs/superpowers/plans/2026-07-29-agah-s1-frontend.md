# جاماسپ S1 Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Next.js application that lets an admin register a data source, watch a scan run, and review the AI's schema descriptions table-by-table in Persian or English — the human-verification loop that the whole product rests on.

**Architecture:** Next.js 15 App Router with server components for data fetching and client components only where interaction demands it. Locale is a route segment (`/fa/...`, `/en/...`), so text direction is decided once at the document level rather than per component. All backend calls go through one typed client that forwards the session cookie. The review screen is a two-pane layout — entity list on one side, an editable card on the other — built for keyboard-driven bulk review of large schemas.

**Tech Stack:** Next.js 15 (App Router), React 19, TypeScript, Tailwind CSS v4, shadcn/ui, next-intl, Vazirmatn (self-hosted), Vitest + React Testing Library, MSW, Playwright.

**Spec:** `docs/superpowers/specs/2026-07-28-jamasp-s1-semantic-layer-design.md` (§6 review UI, §7.3 auth, §7.4 i18n)

**Backend:** complete and on branch `feat/s1-backend`. The API surface this plan consumes is fixed and already tested — see §9 of the spec for the export contract and `apps/api/jamasp/routers/` for the routes.

## Global Constraints

- Package manager is **npm** (pnpm is not installed on this machine; corepack exists but adds a step for no gain). All frontend code under `apps/web/`.
- **Persian is the default locale and RTL is the default direction.** `/` redirects to `/fa`. Direction is set by `<html dir>` from the route segment — never with per-component `dir` attributes or `rtl:` variant soup.
- Every user-facing string lives in `messages/fa.json` and `messages/en.json`. A hardcoded string in a component is a defect; the lint rule in Task 1 enforces it.
- Persian locale renders Persian digits and Jalali dates. English locale renders Latin digits and Gregorian dates.
- The session cookie is httpOnly, so **the browser never reads the token**. Server components forward `cookies()`; client components rely on `credentials: "include"`.
- No API key, DSN, or password may appear in client-side code, a client component prop, or `localStorage`. Credentials are entered in forms and posted directly; they are never read back.
- Components render whatever the API returns without re-deriving business meaning. Human-over-AI text precedence is the API's job (already implemented), not the UI's.
- Tailwind v4 with CSS-first config. shadcn/ui components are vendored into `components/ui/` and edited freely.
- Test command is `npm test` from `apps/web/`. Lint is `npm run lint`. Both clean before every commit.

---

## File Structure

```
apps/web/
  package.json  tsconfig.json  next.config.ts  vitest.config.ts  playwright.config.ts
  messages/
    fa.json                     Persian strings (source of truth)
    en.json                     English strings
  src/
    i18n/
      routing.ts                locales, defaultLocale, direction map
      request.ts                next-intl server config
    middleware.ts               locale routing + auth redirect
    lib/
      api/
        client.ts               typed fetch wrapper, cookie forwarding, error mapping
        types.ts                hand-written mirrors of the API schemas
        sources.ts              source + scan calls
        entities.ts             entity list/detail/patch/approve calls
        settings.ts             LLM settings calls
      format.ts                 locale-aware numbers, dates, percentages
      cn.ts                     class merge helper
    components/
      ui/                       shadcn primitives (button, input, card, badge, ...)
      layout/
        app-shell.tsx           sidebar + header, locale switcher
        locale-switcher.tsx
      sources/
        source-list.tsx
        add-source-dialog.tsx   name/kind/DSN + test-connection
        scan-progress.tsx       SSE consumer
      review/
        entity-list.tsx         filters, search, status chips, progress
        entity-card.tsx         summary + columns + relationships + actions
        field-row.tsx           one column, inline edit
        enum-editor.tsx         coded-column decoding editor
        relationship-panel.tsx  declared vs inferred, accept/reject
        bulk-approve-bar.tsx
      settings/
        provider-form.tsx
        route-table.tsx         per-task model routing
    app/
      [locale]/
        layout.tsx              html lang/dir, fonts, providers
        login/page.tsx
        (app)/
          layout.tsx            app shell, requires session
          sources/page.tsx
          sources/[id]/page.tsx          scan history + start scan
          sources/[id]/review/page.tsx   the review screen
          settings/page.tsx
      globals.css               Tailwind v4 + design tokens + font faces
  tests/
    setup.ts                    RTL + MSW server lifecycle
    mocks/handlers.ts           MSW handlers mirroring the real API
    unit/                       format, client, i18n completeness
    components/                 per-component tests
  e2e/
    review-flow.spec.ts         Playwright, against a live API
```

---

### Task 1: Scaffold, i18n routing, and RTL document shell

**Files:**
- Create: `apps/web/package.json`, `apps/web/tsconfig.json`, `apps/web/next.config.ts`, `apps/web/vitest.config.ts`, `apps/web/src/i18n/routing.ts`, `apps/web/src/i18n/request.ts`, `apps/web/src/middleware.ts`, `apps/web/src/app/[locale]/layout.tsx`, `apps/web/src/app/globals.css`, `apps/web/messages/fa.json`, `apps/web/messages/en.json`, `apps/web/tests/setup.ts`, `apps/web/tests/unit/i18n.test.ts`

**Interfaces:**
- Consumes: nothing
- Produces: `routing` (`{locales: ["fa","en"], defaultLocale: "fa"}`), `directionFor(locale: string): "rtl" | "ltr"`, `Locale` type

- [ ] **Step 1: Write the failing test**

`apps/web/tests/unit/i18n.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import fa from "../../messages/fa.json";
import en from "../../messages/en.json";
import { directionFor, routing } from "../../src/i18n/routing";

function flatten(value: unknown, prefix = ""): string[] {
  if (typeof value !== "object" || value === null) return [prefix];
  return Object.entries(value).flatMap(([key, child]) =>
    flatten(child, prefix ? `${prefix}.${key}` : key),
  );
}

describe("i18n", () => {
  it("defaults to Persian", () => {
    expect(routing.defaultLocale).toBe("fa");
    expect(routing.locales).toEqual(["fa", "en"]);
  });

  it("maps Persian to RTL and English to LTR", () => {
    expect(directionFor("fa")).toBe("rtl");
    expect(directionFor("en")).toBe("ltr");
  });

  it("has identical key sets in both catalogs", () => {
    // A missing key ships as a raw key name to a user. Catch it here, not in prod.
    expect(flatten(en).sort()).toEqual(flatten(fa).sort());
  });

  it("has no empty translations", () => {
    const empties = Object.entries({ fa, en }).flatMap(([locale, catalog]) =>
      JSON.stringify(catalog).includes('""') ? [locale] : [],
    );
    expect(empties).toEqual([]);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/web && npm test -- tests/unit/i18n.test.ts`
Expected: FAIL — cannot resolve `../../src/i18n/routing`

- [ ] **Step 3: Write minimal implementation**

Scaffold with `npx create-next-app@latest apps/web --typescript --tailwind --app --src-dir --no-eslint --use-npm`, then add `next-intl vitest @vitejs/plugin-react @testing-library/react @testing-library/user-event jsdom msw`.

`apps/web/src/i18n/routing.ts`:

```typescript
import { defineRouting } from "next-intl/routing";

export const routing = defineRouting({
  locales: ["fa", "en"],
  defaultLocale: "fa",
});

export type Locale = (typeof routing.locales)[number];

const DIRECTIONS: Record<Locale, "rtl" | "ltr"> = { fa: "rtl", en: "ltr" };

export function directionFor(locale: string): "rtl" | "ltr" {
  return DIRECTIONS[locale as Locale] ?? "ltr";
}
```

`apps/web/src/app/[locale]/layout.tsx` sets direction once, at the document level:

```tsx
import { NextIntlClientProvider } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";
import { directionFor, routing } from "@/i18n/routing";
import "../globals.css";

export function generateStaticParams() {
  return routing.locales.map((locale) => ({ locale }));
}

export default async function LocaleLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  if (!routing.locales.includes(locale as never)) notFound();
  setRequestLocale(locale);
  const messages = await getMessages();

  return (
    <html lang={locale} dir={directionFor(locale)} suppressHydrationWarning>
      <body className="min-h-dvh bg-background text-foreground antialiased">
        <NextIntlClientProvider messages={messages}>{children}</NextIntlClientProvider>
      </body>
    </html>
  );
}
```

`apps/web/src/middleware.ts` wires next-intl's locale negotiation with a matcher that excludes `/api`, `/_next`, and static assets.

`globals.css` declares the Vazirmatn `@font-face` (self-hosted woff2 under `public/fonts/`, so no external CDN request) and Tailwind v4 `@theme` tokens.

Seed both catalogs with the keys used in this task only: `app.name`, `app.tagline`, `nav.sources`, `nav.settings`, `common.save`, `common.cancel`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/web && npm test -- tests/unit/i18n.test.ts`
Expected: PASS — 4 passed

- [ ] **Step 5: Commit**

```bash
git add apps/web
git commit -m "feat(web): scaffold Next.js app with fa/en routing and RTL shell"
```

---

### Task 2: Typed API client

**Files:**
- Create: `apps/web/src/lib/api/types.ts`, `apps/web/src/lib/api/client.ts`, `apps/web/tests/mocks/handlers.ts`, `apps/web/tests/unit/client.test.ts`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `ApiError` (`status: number`, `detail: string`)
  - `apiFetch<T>(path: string, init?: RequestInit): Promise<T>`
  - Types mirroring the backend: `SourceOut`, `ScanOut`, `EntitySummaryOut`, `EntityOut`, `FieldOut`, `EntityListOut`, `Bilingual`, `KnowledgeExport`, `LLMSettings`

- [ ] **Step 1: Write the failing test**

`apps/web/tests/unit/client.test.ts`:

```typescript
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/web && npm test -- tests/unit/client.test.ts`
Expected: FAIL — cannot resolve `../../src/lib/api/client`

- [ ] **Step 3: Write minimal implementation**

`apps/web/src/lib/api/client.ts`:

```typescript
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
  ) {
    super(detail);
    this.name = "ApiError";
  }
}

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    ...init,
    // httpOnly session cookie: the browser attaches it, JS never reads it.
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
  });

  if (!response.ok) {
    let detail = response.statusText || `request failed with ${response.status}`;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      // Non-JSON error body (proxy timeout, gateway page): keep the status text.
    }
    throw new ApiError(response.status, detail);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
```

`apps/web/src/lib/api/types.ts` mirrors the backend schemas by hand — they are small, stable, and a hand-written mirror keeps the build free of a codegen step:

```typescript
export type Bilingual = { fa: string; en: string };

export type SourceKind = "postgres" | "mysql" | "mssql" | "oracle" | "rest" | "mcp";
export type SourceStatus = "draft" | "scanning" | "ready" | "error";
export type EntityStatus =
  | "pending" | "approved" | "stale" | "ignored" | "archived" | "describe_failed";

export interface SourceOut {
  id: string;
  name: string;
  kind: SourceKind;
  sampling_policy: "masked" | "schema_only";
  status: SourceStatus;
  created_at: string;
  last_scan_at: string | null;
}

export interface ScanOut {
  id: string;
  data_source_id: string;
  status: "queued" | "running" | "succeeded" | "partial" | "failed";
  started_at: string | null;
  finished_at: string | null;
  stats: { llm_calls?: number; tokens_in?: number; tokens_out?: number } | null;
  error: { failures?: { entity: string; error: string }[]; fatal?: string } | null;
}

export interface FieldOut {
  id: string;
  name: string;
  data_type: string;
  nullable: boolean;
  is_pk: boolean;
  ordinal: number;
  meaning_ai: Bilingual | null;
  meaning_human: Bilingual | null;
  enum_map: Record<string, Bilingual> | null;
  unit: string | null;
  pii_class: "none" | "low" | "high";
  confidence: number | null;
}

export interface EntitySummaryOut {
  id: string;
  kind: string;
  schema_name: string;
  name: string;
  status: EntityStatus;
  confidence: number | null;
  row_count_approx: number | null;
  version: number;
}

export interface EntityOut extends EntitySummaryOut {
  structural: Record<string, unknown>;
  description_ai: Record<string, unknown> | null;
  description_human: Record<string, unknown> | null;
  approved_by: string | null;
  approved_at: string | null;
  fields: FieldOut[];
}

export interface EntityListOut {
  items: EntitySummaryOut[];
  total: number;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/web && npm test -- tests/unit/client.test.ts`
Expected: PASS — 5 passed

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/lib apps/web/tests
git commit -m "feat(web): add typed API client with cookie forwarding"
```

---

### Task 3: Locale-aware formatting

**Files:**
- Create: `apps/web/src/lib/format.ts`, `apps/web/tests/unit/format.test.ts`

**Interfaces:**
- Consumes: `Locale` (Task 1)
- Produces: `formatNumber(value, locale)`, `formatDate(value, locale)`, `formatPercent(value, locale)`, `formatConfidence(value, locale)`

Built before any screen because every screen shows counts, dates and confidence scores, and Persian requires different digits *and* a different calendar.

- [ ] **Step 1: Write the failing test**

`apps/web/tests/unit/format.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import { formatConfidence, formatDate, formatNumber, formatPercent } from "../../src/lib/format";

describe("formatNumber", () => {
  it("uses Persian digits for fa", () => {
    expect(formatNumber(148230, "fa")).toBe("۱۴۸٬۲۳۰");
  });

  it("uses Latin digits for en", () => {
    expect(formatNumber(148230, "en")).toBe("148,230");
  });
});

describe("formatDate", () => {
  it("uses the Jalali calendar for fa", () => {
    // 2026-07-29 Gregorian falls in year 1405 of the Jalali calendar.
    expect(formatDate("2026-07-29T12:00:00Z", "fa")).toContain("۱۴۰۵");
  });

  it("uses the Gregorian calendar for en", () => {
    expect(formatDate("2026-07-29T12:00:00Z", "en")).toContain("2026");
  });

  it("renders an em dash for a null timestamp", () => {
    expect(formatDate(null, "en")).toBe("—");
  });
});

describe("formatPercent", () => {
  it("formats a ratio as a percentage", () => {
    expect(formatPercent(0.86, "en")).toBe("86%");
  });
});

describe("formatConfidence", () => {
  it("renders an em dash when confidence is unknown", () => {
    // An unscored entity must not read as 0% confidence — that is a different claim.
    expect(formatConfidence(null, "en")).toBe("—");
  });

  it("formats a known score as a percentage", () => {
    expect(formatConfidence(0.95, "en")).toBe("95%");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/web && npm test -- tests/unit/format.test.ts`
Expected: FAIL — cannot resolve `../../src/lib/format`

- [ ] **Step 3: Write minimal implementation**

`apps/web/src/lib/format.ts`:

```typescript
import type { Locale } from "@/i18n/routing";

const EMPTY = "—";

const LOCALE_TAGS: Record<Locale, string> = {
  fa: "fa-IR-u-nu-arabext-ca-persian",
  en: "en-US",
};

function tag(locale: string): string {
  return LOCALE_TAGS[locale as Locale] ?? LOCALE_TAGS.en;
}

export function formatNumber(value: number | null | undefined, locale: string): string {
  if (value === null || value === undefined) return EMPTY;
  return new Intl.NumberFormat(tag(locale)).format(value);
}

export function formatDate(value: string | null | undefined, locale: string): string {
  if (!value) return EMPTY;
  return new Intl.DateTimeFormat(tag(locale), {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export function formatPercent(value: number | null | undefined, locale: string): string {
  if (value === null || value === undefined) return EMPTY;
  return new Intl.NumberFormat(tag(locale), {
    style: "percent",
    maximumFractionDigits: 0,
  }).format(value);
}

// Distinct from formatPercent so "not scored" never renders as "0%".
export const formatConfidence = formatPercent;
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/web && npm test -- tests/unit/format.test.ts`
Expected: PASS — 8 passed

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/lib/format.ts apps/web/tests/unit/format.test.ts
git commit -m "feat(web): add locale-aware number, date and confidence formatting"
```

---

### Task 4: Login and session guard

**Files:**
- Create: `apps/web/src/app/[locale]/login/page.tsx`, `apps/web/src/components/auth/login-form.tsx`, `apps/web/src/lib/api/auth.ts`, `apps/web/tests/components/login-form.test.tsx`
- Modify: `apps/web/src/middleware.ts`, `apps/web/messages/fa.json`, `apps/web/messages/en.json`

**Interfaces:**
- Consumes: `apiFetch`, `ApiError` (Task 2)
- Produces: `login(email, password): Promise<UserOut>`, `logout(): Promise<void>`, `getCurrentUser(): Promise<UserOut | null>`, `UserOut` (`{id, email, role: "admin" | "analyst", locale}`)

- [ ] **Step 1: Write the failing test**

`apps/web/tests/components/login-form.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { NextIntlClientProvider } from "next-intl";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { LoginForm } from "../../src/components/auth/login-form";
import messages from "../../messages/en.json";

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

    await userEvent.type(screen.getByLabelText(/email/i), "admin@jamasp.local");
    await userEvent.type(screen.getByLabelText(/password/i), "correct-horse");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

    expect(onSuccess).toHaveBeenCalledWith(
      expect.objectContaining({ role: "admin" }),
    );
  });

  it("shows the server's message when credentials are rejected", async () => {
    server.use(
      http.post("*/api/auth/login", () =>
        HttpResponse.json({ detail: "invalid email or password" }, { status: 401 }),
      ),
    );
    renderForm();

    await userEvent.type(screen.getByLabelText(/email/i), "admin@jamasp.local");
    await userEvent.type(screen.getByLabelText(/password/i), "wrong");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("invalid email or password");
  });

  it("never renders the password back into the DOM as plain text", async () => {
    renderForm();
    const password = screen.getByLabelText(/password/i);
    await userEvent.type(password, "correct-horse");
    expect(password).toHaveAttribute("type", "password");
    expect(document.body.innerHTML).not.toContain("correct-horse");
  });

  it("disables the submit button while the request is in flight", async () => {
    server.use(
      http.post("*/api/auth/login", async () => {
        await new Promise((resolve) => setTimeout(resolve, 50));
        return HttpResponse.json({ id: "1", email: "a@b.c", role: "admin", locale: "fa" });
      }),
    );
    renderForm();

    await userEvent.type(screen.getByLabelText(/email/i), "admin@jamasp.local");
    await userEvent.type(screen.getByLabelText(/password/i), "correct-horse");
    const button = screen.getByRole("button", { name: /sign in/i });
    await userEvent.click(button);

    expect(button).toBeDisabled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/web && npm test -- tests/components/login-form.test.tsx`
Expected: FAIL — cannot resolve `../../src/components/auth/login-form`

- [ ] **Step 3: Write minimal implementation**

`apps/web/src/lib/api/auth.ts`:

```typescript
import { apiFetch, ApiError } from "./client";

export interface UserOut {
  id: string;
  email: string;
  role: "admin" | "analyst";
  locale: string;
}

export function login(email: string, password: string): Promise<UserOut> {
  return apiFetch<UserOut>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function logout(): Promise<void> {
  return apiFetch<void>("/api/auth/logout", { method: "POST" });
}

export async function getCurrentUser(): Promise<UserOut | null> {
  try {
    return await apiFetch<UserOut>("/api/auth/me");
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null;
    throw error;
  }
}
```

`login-form.tsx` is a client component holding `email`, `password`, `error` and `pending` state. On submit it calls `login()`, surfaces `ApiError.detail` in a `role="alert"` element, and disables the button while pending. The password input keeps `type="password"` and is never echoed into any other node.

Extend `middleware.ts`: an unauthenticated request to anything under `(app)` redirects to `/{locale}/login`; an authenticated request to `/login` redirects to `/{locale}/sources`. Presence of the session cookie is the signal — the middleware cannot decode it, and does not need to.

Add message keys: `auth.email`, `auth.password`, `auth.signIn`, `auth.signOut`, `auth.title`, `auth.subtitle`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/web && npm test -- tests/components/login-form.test.tsx`
Expected: PASS — 4 passed

- [ ] **Step 5: Commit**

```bash
git add apps/web
git commit -m "feat(web): add login form and session guard middleware"
```

---

### Task 5: Sources list and add-source wizard

**Files:**
- Create: `apps/web/src/lib/api/sources.ts`, `apps/web/src/components/sources/source-list.tsx`, `apps/web/src/components/sources/add-source-dialog.tsx`, `apps/web/src/app/[locale]/(app)/sources/page.tsx`, `apps/web/src/components/layout/app-shell.tsx`, `apps/web/src/components/layout/locale-switcher.tsx`, `apps/web/tests/components/add-source-dialog.test.tsx`
- Modify: `apps/web/messages/fa.json`, `apps/web/messages/en.json`

**Interfaces:**
- Consumes: `apiFetch` (Task 2), `formatDate` (Task 3)
- Produces: `listSources()`, `createSource(input)`, `testConnection(kind, dsn)`, `deleteSource(id)`, `startScan(sourceId): Promise<ScanOut>`

- [ ] **Step 1: Write the failing test**

`apps/web/tests/components/add-source-dialog.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { NextIntlClientProvider } from "next-intl";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { AddSourceDialog } from "../../src/components/sources/add-source-dialog";
import messages from "../../messages/en.json";

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "bypass" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function renderDialog(onCreated = vi.fn()) {
  render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <AddSourceDialog open onOpenChange={() => {}} onCreated={onCreated} />
    </NextIntlClientProvider>,
  );
  return onCreated;
}

describe("AddSourceDialog", () => {
  it("reports a failed connection test with the driver's own message", async () => {
    server.use(
      http.post("*/api/sources/test-connection", () =>
        HttpResponse.json({ healthy: false, error: 'password authentication failed' }),
      ),
    );
    renderDialog();

    await userEvent.type(screen.getByLabelText(/name/i), "HR");
    await userEvent.type(screen.getByLabelText(/connection/i), "postgresql://x");
    await userEvent.click(screen.getByRole("button", { name: /test connection/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "password authentication failed",
    );
  });

  it("confirms a healthy connection before allowing save", async () => {
    server.use(
      http.post("*/api/sources/test-connection", () =>
        HttpResponse.json({ healthy: true, server_version: "PostgreSQL 16.2" }),
      ),
    );
    renderDialog();

    await userEvent.type(screen.getByLabelText(/name/i), "HR");
    await userEvent.type(screen.getByLabelText(/connection/i), "postgresql://x");
    await userEvent.click(screen.getByRole("button", { name: /test connection/i }));

    expect(await screen.findByText(/PostgreSQL 16.2/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^save$/i })).toBeEnabled();
  });

  it("keeps save disabled until a connection has been proven", () => {
    renderDialog();
    expect(screen.getByRole("button", { name: /^save$/i })).toBeDisabled();
  });

  it("masks the connection string input", async () => {
    renderDialog();
    expect(screen.getByLabelText(/connection/i)).toHaveAttribute("type", "password");
  });

  it("calls onCreated with the new source and never echoes the DSN", async () => {
    server.use(
      http.post("*/api/sources/test-connection", () =>
        HttpResponse.json({ healthy: true, server_version: "PostgreSQL 16.2" }),
      ),
      http.post("*/api/sources", () =>
        HttpResponse.json(
          { id: "s1", name: "HR", kind: "postgres", status: "draft" },
          { status: 201 },
        ),
      ),
    );
    const onCreated = renderDialog();

    await userEvent.type(screen.getByLabelText(/name/i), "HR");
    await userEvent.type(screen.getByLabelText(/connection/i), "postgresql://secret@db/hr");
    await userEvent.click(screen.getByRole("button", { name: /test connection/i }));
    await screen.findByText(/PostgreSQL 16.2/);
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    expect(onCreated).toHaveBeenCalledWith(expect.objectContaining({ id: "s1" }));
    expect(document.body.innerHTML).not.toContain("secret");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/web && npm test -- tests/components/add-source-dialog.test.tsx`
Expected: FAIL — cannot resolve `../../src/components/sources/add-source-dialog`

- [ ] **Step 3: Write minimal implementation**

`apps/web/src/lib/api/sources.ts`:

```typescript
import { apiFetch } from "./client";
import type { ScanOut, SourceKind, SourceOut } from "./types";

export interface ConnectionTestResult {
  healthy: boolean;
  server_version: string;
  error: string | null;
}

export function listSources(): Promise<SourceOut[]> {
  return apiFetch<SourceOut[]>("/api/sources");
}

export function createSource(input: {
  name: string;
  kind: SourceKind;
  dsn: string;
  sampling_policy?: "masked" | "schema_only";
}): Promise<SourceOut> {
  return apiFetch<SourceOut>("/api/sources", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function testConnection(kind: SourceKind, dsn: string): Promise<ConnectionTestResult> {
  return apiFetch<ConnectionTestResult>("/api/sources/test-connection", {
    method: "POST",
    body: JSON.stringify({ kind, dsn }),
  });
}

export function deleteSource(id: string): Promise<void> {
  return apiFetch<void>(`/api/sources/${id}`, { method: "DELETE" });
}

export function startScan(sourceId: string): Promise<ScanOut> {
  return apiFetch<ScanOut>(`/api/sources/${sourceId}/scans`, { method: "POST" });
}
```

`add-source-dialog.tsx` holds `name`, `kind`, `dsn`, `samplingPolicy`, `testResult` and `error`. Save stays disabled until `testResult?.healthy` is true — registering a source that cannot be reached only produces a failed scan later. The DSN input is `type="password"` and lives in component state only; after a successful create the dialog closes and the state is dropped.

`source-list.tsx` renders a table of name, kind, status badge, last scan (via `formatDate`) and a row action to open the source. `app-shell.tsx` provides the sidebar, header and locale switcher; the switcher swaps the locale segment of the current path so the user stays on the same screen.

Add message keys under `sources.*` and `common.*` for every visible string.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/web && npm test -- tests/components/add-source-dialog.test.tsx`
Expected: PASS — 5 passed

- [ ] **Step 5: Commit**

```bash
git add apps/web
git commit -m "feat(web): add sources list and connection-tested add-source wizard"
```

---

### Task 6: Scan progress over SSE

**Files:**
- Create: `apps/web/src/components/sources/scan-progress.tsx`, `apps/web/src/lib/api/scans.ts`, `apps/web/src/app/[locale]/(app)/sources/[id]/page.tsx`, `apps/web/tests/components/scan-progress.test.tsx`
- Modify: `apps/web/messages/fa.json`, `apps/web/messages/en.json`

**Interfaces:**
- Consumes: `apiFetch` (Task 2), `formatNumber` (Task 3)
- Produces: `getScan(id)`, `scanEventsUrl(id): string`, `ProgressEvent` (`{stage, current, total, message}`), `useScanProgress(scanId): {events, latest, done, status}`

- [ ] **Step 1: Write the failing test**

`apps/web/tests/components/scan-progress.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ScanProgress } from "../../src/components/sources/scan-progress";
import messages from "../../messages/en.json";

class MockEventSource {
  static instances: MockEventSource[] = [];
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: ((event: unknown) => void) | null = null;
  closed = false;

  constructor(readonly url: string) {
    MockEventSource.instances.push(this);
  }

  emit(payload: object) {
    this.onmessage?.({ data: JSON.stringify(payload) });
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
    source.emit({ stage: "introspect", current: 0, total: 1, message: "reading schema" });
    expect(await screen.findByText(/reading schema/i)).toBeInTheDocument();
  });

  it("shows per-entity progress during the describe stage", async () => {
    const source = renderProgress();
    source.emit({ stage: "describe", current: 3, total: 12, message: "leave_requests" });

    expect(await screen.findByText(/leave_requests/)).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "3");
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuemax", "12");
  });

  it("closes the connection when the terminal event arrives", async () => {
    const source = renderProgress();
    source.emit({ stage: "done", status: "succeeded" });
    await waitFor(() => expect(source.closed).toBe(true));
  });

  it("surfaces a partial scan distinctly from a successful one", async () => {
    const source = renderProgress();
    source.emit({ stage: "done", status: "partial" });
    // A partial scan means some tables failed to describe; it must not read as success.
    expect(await screen.findByText(/partial/i)).toBeInTheDocument();
  });

  it("reports a dropped connection instead of hanging silently", async () => {
    const source = renderProgress();
    source.onerror?.(new Event("error"));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/web && npm test -- tests/components/scan-progress.test.tsx`
Expected: FAIL — cannot resolve `../../src/components/sources/scan-progress`

- [ ] **Step 3: Write minimal implementation**

`apps/web/src/lib/api/scans.ts`:

```typescript
import { apiFetch } from "./client";
import type { ScanOut } from "./types";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface ProgressEvent {
  stage: "introspect" | "profile" | "probe" | "describe" | "embed" | "diff" | "done" | "status";
  current?: number;
  total?: number;
  message?: string;
  status?: string;
}

export function getScan(id: string): Promise<ScanOut> {
  return apiFetch<ScanOut>(`/api/scans/${id}`);
}

export function scanEventsUrl(id: string): string {
  return `${BASE_URL}/api/scans/${id}/events`;
}
```

`scan-progress.tsx` is a client component. A `useEffect` opens `new EventSource(scanEventsUrl(scanId), { withCredentials: true })`, appends each parsed event to state, and closes the connection when `stage === "done"`. It renders the stage name from the message catalog, the `message` field verbatim (it carries entity names), and a `role="progressbar"` with `aria-valuenow`/`aria-valuemax` when `total` is present. `onerror` sets an error state rendered as `role="alert"`, so a dropped stream is visible rather than a frozen bar.

The source detail page lists past scans with their token cost from `stats`, and starts a new scan.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/web && npm test -- tests/components/scan-progress.test.tsx`
Expected: PASS — 5 passed

- [ ] **Step 5: Commit**

```bash
git add apps/web
git commit -m "feat(web): stream scan progress over SSE with live stage reporting"
```

---

### Task 7: Entity list with filters and review progress

**Files:**
- Create: `apps/web/src/lib/api/entities.ts`, `apps/web/src/components/review/entity-list.tsx`, `apps/web/src/app/[locale]/(app)/sources/[id]/review/page.tsx`, `apps/web/tests/components/entity-list.test.tsx`
- Modify: `apps/web/messages/fa.json`, `apps/web/messages/en.json`

**Interfaces:**
- Consumes: `apiFetch` (Task 2), `formatConfidence`, `formatNumber` (Task 3), `EntitySummaryOut`, `EntityListOut` (Task 2)
- Produces: `listEntities(sourceId, params)`, `getEntity(id)`, `patchEntity(id, patch)`, `approveEntity(id)`, `ignoreEntity(id)`, `bulkApprove(sourceId, minConfidence)`

- [ ] **Step 1: Write the failing test**

`apps/web/tests/components/entity-list.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it, vi } from "vitest";
import { EntityList } from "../../src/components/review/entity-list";
import messages from "../../messages/en.json";
import type { EntitySummaryOut } from "../../src/lib/api/types";

const ENTITIES: EntitySummaryOut[] = [
  { id: "1", kind: "table", schema_name: "public", name: "employees",
    status: "approved", confidence: 0.95, row_count_approx: 3, version: 1 },
  { id: "2", kind: "table", schema_name: "public", name: "leave_requests",
    status: "pending", confidence: 0.62, row_count_approx: 4, version: 1 },
  { id: "3", kind: "table", schema_name: "public", name: "t_mst_01",
    status: "describe_failed", confidence: null, row_count_approx: 3, version: 1 },
];

function renderList(props: Partial<React.ComponentProps<typeof EntityList>> = {}) {
  const onSelect = vi.fn();
  const onFilterChange = vi.fn();
  render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <EntityList
        entities={ENTITIES}
        total={3}
        approvedCount={1}
        selectedId="2"
        onSelect={onSelect}
        onFilterChange={onFilterChange}
        {...props}
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
    const selected = screen.getByRole("option", { name: /leave_requests/ });
    expect(selected).toHaveAttribute("aria-selected", "true");
  });

  it("calls onSelect when an entity is clicked", async () => {
    const { onSelect } = renderList();
    await userEvent.click(screen.getByRole("option", { name: /employees/ }));
    expect(onSelect).toHaveBeenCalledWith("1");
  });

  it("requests a status filter when one is chosen", async () => {
    const { onFilterChange } = renderList();
    await userEvent.selectOptions(screen.getByLabelText(/status/i), "pending");
    expect(onFilterChange).toHaveBeenCalledWith(
      expect.objectContaining({ status: "pending" }),
    );
  });

  it("flags a failed description distinctly from a low-confidence one", () => {
    renderList();
    const failed = screen.getByRole("option", { name: /t_mst_01/ });
    // describe_failed needs a retry, low confidence needs a read. Different actions.
    expect(failed).toHaveTextContent(/failed/i);
    expect(failed).not.toHaveTextContent("0%");
  });

  it("renders an em dash rather than 0% when confidence is unknown", () => {
    renderList();
    expect(screen.getByRole("option", { name: /t_mst_01/ })).toHaveTextContent("—");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/web && npm test -- tests/components/entity-list.test.tsx`
Expected: FAIL — cannot resolve `../../src/components/review/entity-list`

- [ ] **Step 3: Write minimal implementation**

`apps/web/src/lib/api/entities.ts`:

```typescript
import { apiFetch } from "./client";
import type { EntityListOut, EntityOut, EntityStatus } from "./types";

export interface EntityFilters {
  status?: EntityStatus;
  min_confidence?: number;
  q?: string;
  sort?: "name" | "confidence_asc" | "status";
  limit?: number;
  offset?: number;
}

export function listEntities(
  sourceId: string,
  filters: EntityFilters = {},
): Promise<EntityListOut> {
  const query = new URLSearchParams(
    Object.entries(filters)
      .filter(([, value]) => value !== undefined && value !== "")
      .map(([key, value]) => [key, String(value)]),
  );
  return apiFetch<EntityListOut>(`/api/sources/${sourceId}/entities?${query}`);
}

export function getEntity(id: string): Promise<EntityOut> {
  return apiFetch<EntityOut>(`/api/entities/${id}`);
}

export function patchEntity(
  id: string,
  patch: {
    description_human?: Record<string, unknown>;
    fields?: { id: string; meaning_human?: unknown; enum_map?: unknown; unit?: string }[];
  },
): Promise<EntityOut> {
  return apiFetch<EntityOut>(`/api/entities/${id}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export function approveEntity(id: string): Promise<EntityOut> {
  return apiFetch<EntityOut>(`/api/entities/${id}/approve`, { method: "POST" });
}

export function ignoreEntity(id: string): Promise<EntityOut> {
  return apiFetch<EntityOut>(`/api/entities/${id}/ignore`, { method: "POST" });
}

export function bulkApprove(
  sourceId: string,
  minConfidence: number,
): Promise<{ approved_count: number }> {
  return apiFetch<{ approved_count: number }>(
    `/api/sources/${sourceId}/entities/bulk-approve`,
    { method: "POST", body: JSON.stringify({ min_confidence: minConfidence }) },
  );
}
```

`entity-list.tsx` renders a `role="listbox"` of `role="option"` rows, each showing name, status badge, and confidence via `formatConfidence` (so `null` renders `—`, never `0%`). A header shows `approvedCount / total`. Filter controls emit `onFilterChange` with a partial `EntityFilters`. Arrow-key navigation moves selection so a reviewer can work a long list without the mouse.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/web && npm test -- tests/components/entity-list.test.tsx`
Expected: PASS — 6 passed

- [ ] **Step 5: Commit**

```bash
git add apps/web
git commit -m "feat(web): add entity list with filters, progress and keyboard navigation"
```

---

### Task 8: Entity card with inline editing and approval

**Files:**
- Create: `apps/web/src/components/review/entity-card.tsx`, `apps/web/src/components/review/field-row.tsx`, `apps/web/src/components/review/enum-editor.tsx`, `apps/web/src/components/review/relationship-panel.tsx`, `apps/web/tests/components/entity-card.test.tsx`
- Modify: `apps/web/messages/fa.json`, `apps/web/messages/en.json`

**Interfaces:**
- Consumes: `patchEntity`, `approveEntity`, `ignoreEntity` (Task 7), `EntityOut`, `FieldOut` (Task 2), `formatConfidence` (Task 3)
- Produces: `EntityCard` props `{entity: EntityOut, locale: Locale, onChanged: (entity: EntityOut) => void, onApproved: () => void}`

This is the screen the product exists for. Its job is to make the AI's claim inspectable and the correction cheap.

- [ ] **Step 1: Write the failing test**

`apps/web/tests/components/entity-card.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { NextIntlClientProvider } from "next-intl";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { EntityCard } from "../../src/components/review/entity-card";
import messages from "../../messages/en.json";
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
  approved_by: null, approved_at: null,
  fields: [
    { id: "f1", name: "id", data_type: "INTEGER", nullable: false, is_pk: true, ordinal: 0,
      meaning_ai: { fa: "شناسه", en: "Identifier" }, meaning_human: null,
      enum_map: null, unit: null, pii_class: "none", confidence: 0.99 },
    { id: "f2", name: "status", data_type: "SMALLINT", nullable: false, is_pk: false, ordinal: 1,
      meaning_ai: { fa: "وضعیت", en: "Status" }, meaning_human: null,
      enum_map: {
        "1": { fa: "در انتظار", en: "pending" },
        "2": { fa: "تایید شده", en: "approved" },
      },
      unit: null, pii_class: "none", confidence: 0.95 },
    { id: "f3", name: "national_id", data_type: "CHAR(10)", nullable: true, is_pk: false,
      ordinal: 2, meaning_ai: { fa: "کد ملی", en: "National ID" }, meaning_human: null,
      enum_map: null, unit: null, pii_class: "high", confidence: 0.9 },
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
    // Both must be on screen: the human text is the answer, the AI text is the audit trail.
    expect(screen.getByText("My own wording")).toBeInTheDocument();
    expect(screen.getByText(/Employee leave requests/)).toBeInTheDocument();
  });

  it("saves an edited summary as description_human", async () => {
    let body: unknown;
    server.use(
      http.patch("*/api/entities/e1", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ ...ENTITY, description_human: body });
      }),
    );
    const { onChanged } = renderCard();

    await userEvent.click(screen.getByRole("button", { name: /edit summary/i }));
    const box = screen.getByRole("textbox", { name: /summary/i });
    await userEvent.clear(box);
    await userEvent.type(box, "Corrected wording");
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    expect(body).toMatchObject({
      description_human: { summary: { en: "Corrected wording" } },
    });
    expect(onChanged).toHaveBeenCalled();
  });

  it("renders the enum decoding for a coded column", () => {
    renderCard();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("approved")).toBeInTheDocument();
  });

  it("marks a high-PII column so the reviewer knows it was never sampled", () => {
    renderCard();
    const row = screen.getByRole("row", { name: /national_id/ });
    expect(row).toHaveTextContent(/high/i);
  });

  it("approves the entity and reports it upward", async () => {
    server.use(
      http.post("*/api/entities/e1/approve", () =>
        HttpResponse.json({ ...ENTITY, status: "approved" }),
      ),
    );
    const { onApproved } = renderCard();

    await userEvent.click(screen.getByRole("button", { name: /^approve$/i }));
    expect(onApproved).toHaveBeenCalled();
  });

  it("shows a structural diff prompt for a stale entity", () => {
    renderCard({ ...ENTITY, status: "stale" });
    // Stale means the table changed after approval; the reviewer needs that context.
    expect(screen.getByText(/changed since/i)).toBeInTheDocument();
  });

  it("offers a retry rather than an approve for a failed description", () => {
    renderCard({ ...ENTITY, status: "describe_failed", description_ai: null });
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^approve$/i })).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/web && npm test -- tests/components/entity-card.test.tsx`
Expected: FAIL — cannot resolve `../../src/components/review/entity-card`

- [ ] **Step 3: Write minimal implementation**

`entity-card.tsx` is a client component composed of:

- **Header** — schema-qualified name, kind, row count via `formatNumber`, status badge, confidence via `formatConfidence`.
- **Summary block** — human text when present, otherwise AI text; an "edit summary" control swaps in a textarea; saving PATCHes `description_human` for the active locale and merges the response through `onChanged`. When human text exists, the AI original stays rendered beneath it under an "AI suggested" label — the audit trail the spec calls for.
- **Column table** — one `field-row.tsx` per column with name, type, meaning (inline editable), PII badge and confidence. Low-confidence rows carry a visual flag.
- **`enum-editor.tsx`** — for any field with `enum_map`, a code → label grid editable in both locales; this is where a reviewer fixes `status=3` meaning "rejected" rather than "cancelled".
- **`relationship-panel.tsx`** — declared foreign keys read-only; inferred ones show the join-probe hit rate as evidence with accept/reject.
- **Actions** — Approve, Approve & next, Ignore. For `describe_failed` the approve action is replaced by Retry (which POSTs to the redescribe endpoint), because approving a description that does not exist is meaningless. For `stale`, a banner explains the entity changed after approval.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/web && npm test -- tests/components/entity-card.test.tsx`
Expected: PASS — 8 passed

- [ ] **Step 5: Commit**

```bash
git add apps/web
git commit -m "feat(web): add entity review card with inline edit and enum decoding"
```

---

### Task 9: Bulk approve and settings screen

**Files:**
- Create: `apps/web/src/components/review/bulk-approve-bar.tsx`, `apps/web/src/lib/api/settings.ts`, `apps/web/src/components/settings/provider-form.tsx`, `apps/web/src/components/settings/route-table.tsx`, `apps/web/src/app/[locale]/(app)/settings/page.tsx`, `apps/web/tests/components/bulk-approve-bar.test.tsx`, `apps/web/tests/components/route-table.test.tsx`
- Modify: `apps/web/messages/fa.json`, `apps/web/messages/en.json`

**Interfaces:**
- Consumes: `bulkApprove` (Task 7), `apiFetch` (Task 2)
- Produces: `getLLMSettings()`, `updateProviders(providers)`, `updateRoutes(routes)`, `LLMSettings` (`{providers: Record<string, {base_url, api_key, extra_headers}>, routes: Record<string, {provider, model, temperature, fallbacks}>}`)

- [ ] **Step 1: Write the failing test**

`apps/web/tests/components/bulk-approve-bar.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it, vi } from "vitest";
import { BulkApproveBar } from "../../src/components/review/bulk-approve-bar";
import messages from "../../messages/en.json";

function renderBar() {
  const onApprove = vi.fn();
  render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <BulkApproveBar pendingCount={47} onApprove={onApprove} />
    </NextIntlClientProvider>,
  );
  return { onApprove };
}

describe("BulkApproveBar", () => {
  it("requires confirmation before approving in bulk", async () => {
    const { onApprove } = renderBar();
    await userEvent.click(screen.getByRole("button", { name: /approve all above/i }));
    // Bulk approval is the one action that can rubber-stamp the human gate.
    expect(onApprove).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("passes the chosen threshold once confirmed", async () => {
    const { onApprove } = renderBar();
    await userEvent.click(screen.getByRole("button", { name: /approve all above/i }));
    await userEvent.click(screen.getByRole("button", { name: /^confirm$/i }));
    expect(onApprove).toHaveBeenCalledWith(0.8);
  });

  it("states how many entities the action will affect", async () => {
    renderBar();
    await userEvent.click(screen.getByRole("button", { name: /approve all above/i }));
    expect(screen.getByRole("dialog")).toHaveTextContent("47");
  });
});
```

`apps/web/tests/components/route-table.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it, vi } from "vitest";
import { RouteTable } from "../../src/components/settings/route-table";
import messages from "../../messages/en.json";

const ROUTES = {
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
    expect(screen.getByText("nvidia/nemotron-3-ultra-550b-a55b:free")).toBeInTheDocument();
    expect(screen.getByText("bge-m3")).toBeInTheDocument();
  });

  it("switches a task to a local model without touching any other task", async () => {
    const { onSave } = renderTable();
    const row = screen.getByRole("row", { name: /describe_entity/ });
    await userEvent.selectOptions(within(row).getByLabelText(/provider/i), "local");
    await userEvent.clear(within(row).getByLabelText(/model/i));
    await userEvent.type(within(row).getByLabelText(/model/i), "qwen2.5:32b");
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    expect(onSave).toHaveBeenCalledWith({
      describe_entity: expect.objectContaining({ provider: "local", model: "qwen2.5:32b" }),
    });
  });
});
```

Add `import { within } from "@testing-library/react";` to the second file.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/web && npm test -- tests/components/bulk-approve-bar.test.tsx tests/components/route-table.test.tsx`
Expected: FAIL — cannot resolve the two component modules

- [ ] **Step 3: Write minimal implementation**

`bulk-approve-bar.tsx` shows the pending count, a confidence-threshold selector (default 0.8) and an "approve all above" button that opens a confirmation dialog naming the count. Only on confirm does it call `onApprove(threshold)` — bulk approval is the one action capable of rubber-stamping the human gate the product is built around, so it gets a deliberate stop.

`apps/web/src/lib/api/settings.ts`:

```typescript
import { apiFetch } from "./client";

export interface ProviderConfig {
  base_url: string;
  api_key: string;
  extra_headers: Record<string, string> | null;
}

export interface RouteConfig {
  provider: string;
  model: string;
  temperature: number;
  fallbacks: [string, string][];
}

export interface LLMSettings {
  providers: Record<string, ProviderConfig>;
  routes: Record<string, RouteConfig>;
}

export function getLLMSettings(): Promise<LLMSettings> {
  return apiFetch<LLMSettings>("/api/settings/llm");
}

export function updateProviders(
  providers: Record<string, ProviderConfig>,
): Promise<LLMSettings> {
  return apiFetch<LLMSettings>("/api/settings/llm/providers", {
    method: "PUT",
    body: JSON.stringify({ providers }),
  });
}

export function updateRoutes(routes: Record<string, RouteConfig>): Promise<LLMSettings> {
  return apiFetch<LLMSettings>("/api/settings/llm/routes", {
    method: "PUT",
    body: JSON.stringify({ routes }),
  });
}
```

`provider-form.tsx` renders base URL and API key per provider. The key field shows the API's `••••••••` placeholder and only sends a new value when the admin actually types one — submitting the placeholder back would overwrite a real key with dots. `route-table.tsx` renders one row per task with provider select and model input, and saves only the rows that changed.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/web && npm test -- tests/components/bulk-approve-bar.test.tsx tests/components/route-table.test.tsx`
Expected: PASS — 5 passed

- [ ] **Step 5: Commit**

```bash
git add apps/web
git commit -m "feat(web): add guarded bulk approve and LLM settings screens"
```

---

### Task 10: End-to-end review flow

**Files:**
- Create: `apps/web/playwright.config.ts`, `apps/web/e2e/review-flow.spec.ts`, `docker/compose.dev.yml`, `apps/web/README.md`

**Interfaces:**
- Consumes: everything above, plus the live backend
- Produces: a runnable full-stack development environment and the acceptance test for S1's UI

- [ ] **Step 1: Write the failing test**

`apps/web/e2e/review-flow.spec.ts`:

```typescript
import { expect, test } from "@playwright/test";

test.describe("review flow", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/fa/login");
    await page.getByLabel(/ایمیل|email/i).fill("admin@jamasp.local");
    await page.getByLabel(/گذرواژه|password/i).fill(process.env.JAMASP_ADMIN_PASSWORD!);
    await page.getByRole("button", { name: /ورود|sign in/i }).click();
    await expect(page).toHaveURL(/\/fa\/sources/);
  });

  test("Persian is the default locale and the document is RTL", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/fa/);
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  });

  test("switching to English flips direction and keeps the current screen", async ({ page }) => {
    await page.getByRole("button", { name: /English/i }).click();
    await expect(page).toHaveURL(/\/en\/sources/);
    await expect(page.locator("html")).toHaveAttribute("dir", "ltr");
  });

  test("registers a source, scans it, reviews and approves", async ({ page }) => {
    await page.getByRole("button", { name: /افزودن|add source/i }).click();
    await page.getByLabel(/نام|name/i).fill("HR");
    await page.getByLabel(/اتصال|connection/i).fill(process.env.JAMASP_FIXTURE_DSN!);
    await page.getByRole("button", { name: /آزمایش|test connection/i }).click();
    await expect(page.getByText(/PostgreSQL/)).toBeVisible();
    await page.getByRole("button", { name: /ذخیره|save/i }).click();

    await page.getByRole("link", { name: "HR" }).click();
    await page.getByRole("button", { name: /اسکن|start scan/i }).click();
    await expect(page.getByRole("progressbar")).toBeVisible();
    await expect(page.getByText(/تکمیل|succeeded|partial/i)).toBeVisible({ timeout: 180_000 });

    await page.getByRole("link", { name: /بازبینی|review/i }).click();
    await page.getByRole("option", { name: /leave_requests/ }).click();
    await expect(page.getByText(/مرخصی/)).toBeVisible();

    await page.getByRole("button", { name: /تایید|approve/i }).first().click();
    await expect(page.getByRole("option", { name: /leave_requests/ })).toContainText(
      /تایید شده|approved/i,
    );
  });

  test("a rejected connection is reported before the source is saved", async ({ page }) => {
    await page.getByRole("button", { name: /افزودن|add source/i }).click();
    await page.getByLabel(/نام|name/i).fill("Broken");
    await page.getByLabel(/اتصال|connection/i).fill("postgresql://nobody@127.0.0.1:1/none");
    await page.getByRole("button", { name: /آزمایش|test connection/i }).click();
    await expect(page.getByRole("alert")).toBeVisible();
    await expect(page.getByRole("button", { name: /ذخیره|save/i })).toBeDisabled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/web && npx playwright test`
Expected: FAIL — no dev stack running, `/fa/login` unreachable

- [ ] **Step 3: Write minimal implementation**

`docker/compose.dev.yml` extends the existing stack with the API (`uvicorn jamasp.main:app`), the arq worker (`arq jamasp.pipeline.worker.WorkerSettings`), the web app, and the fixture database, wired so `NEXT_PUBLIC_API_URL` points at the API service.

`playwright.config.ts` sets `baseURL` to `http://localhost:3000`, `webServer` to bring up the dev stack, and one Chromium project.

Add a `seed-admin` invocation to the compose entrypoint so `JAMASP_ADMIN_PASSWORD` creates the first admin, and document the whole loop in `apps/web/README.md`: how to start the stack, where the fixture DSN comes from, and which env vars the e2e run needs.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/web && npx playwright test`
Expected: PASS — 4 passed

- [ ] **Step 5: Commit**

```bash
git add apps/web docker/compose.dev.yml
git commit -m "feat(web): add end-to-end review flow and dev stack"
```

---

## Self-Review

**Spec coverage:**

| Spec section | Covered by |
|---|---|
| §6 entity list, filters, progress | Task 7 |
| §6 entity card, inline edit, AI original retained | Task 8 |
| §6 enum decoding editor | Task 8 (`enum-editor.tsx`) |
| §6 relationships with join-probe evidence | Task 8 (`relationship-panel.tsx`) |
| §6 bulk operations | Task 9 |
| §6 progress "N of M approved", resumable | Task 7 |
| §7.1 per-task model routing UI | Task 9 (`route-table.tsx`) |
| §7.2 secrets never displayed | Tasks 5, 9 (DSN masked; API key placeholder never resubmitted) |
| §7.3 auth, admin-only actions | Task 4 |
| §7.4 fa/en, RTL, Persian digits, Jalali dates | Tasks 1, 3, 10 |
| §12 acceptance criterion 9 (whole flow in both languages) | Task 10 |

**Gap accepted deliberately:** §6's "retranslate from my edit" action is not built. It needs a backend translate endpoint that does not exist yet, and the bilingual describer already emits both languages in one call, so the out-of-sync case only arises after a manual edit. Recorded here rather than silently dropped; it belongs in the S2 cycle alongside the translate task route that already exists in `DEFAULT_ROUTES`.

**Placeholder scan:** no TBDs. Every component task carries real test code; implementation steps that describe composition rather than showing every line (Tasks 8, 9) name the exact files, props and behaviors, and their tests pin the contract.

**Type consistency checked:** `EntitySummaryOut` / `EntityOut` / `FieldOut` / `Bilingual` are defined once in Task 2 and imported unchanged in Tasks 7 and 8. `formatConfidence` (Task 3) is the only confidence renderer, so the `null → "—"` rule holds everywhere. `EntityFilters` (Task 7) is the single filter shape emitted by `onFilterChange`. `ProgressEvent.stage` (Task 6) matches the six stage names the backend orchestrator emits plus `done` and `status`.

---

## Execution Handoff

Plan complete. Two execution options:

**1. Subagent-Driven (recommended)** — a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — tasks executed in this session via executing-plans, batched with checkpoints.
