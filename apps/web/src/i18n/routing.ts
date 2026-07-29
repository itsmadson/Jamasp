import { defineRouting } from "next-intl/routing";

export const routing = defineRouting({
  locales: ["fa", "en"],
  defaultLocale: "fa",
});

export type Locale = (typeof routing.locales)[number];

const DIRECTIONS: Record<Locale, "rtl" | "ltr"> = { fa: "rtl", en: "ltr" };

/**
 * Direction is resolved once, here, and applied to <html>. Components never
 * carry their own dir attribute — that is how RTL bugs get in.
 */
export function directionFor(locale: string): "rtl" | "ltr" {
  return DIRECTIONS[locale as Locale] ?? "ltr";
}
