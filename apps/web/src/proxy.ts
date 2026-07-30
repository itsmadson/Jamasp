import createMiddleware from "next-intl/middleware";
import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { routing } from "./i18n/routing";

// Next 16 renamed the `middleware` file convention to `proxy`; the exported
// function must be named `proxy` (or be the default export).

const SESSION_COOKIE = "jamasp_session";
const PUBLIC_SEGMENTS = ["login"];

const handleI18nRouting = createMiddleware(routing);

export function proxy(request: NextRequest) {
  const response = handleI18nRouting(request);

  const segments = request.nextUrl.pathname.split("/").filter(Boolean);
  const locale = segments[0] ?? routing.defaultLocale;
  if (!routing.locales.includes(locale as never)) return response;

  // Presence of the cookie is the only signal available here: it is httpOnly and
  // signed, so the proxy cannot decode it and does not need to. The API remains
  // the authority — this redirect only saves a pointless round trip.
  const hasSession = request.cookies.has(SESSION_COOKIE);
  const isPublic = PUBLIC_SEGMENTS.includes(segments[1] ?? "");

  if (!hasSession && !isPublic) {
    return NextResponse.redirect(new URL(`/${locale}/login`, request.url));
  }
  if (hasSession && isPublic) {
    return NextResponse.redirect(new URL(`/${locale}/sources`, request.url));
  }

  return response;
}

export const config = {
  matcher: ["/((?!api|_next|_vercel|.*\\..*).*)"],
};
