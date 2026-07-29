import type { Locale } from "@/i18n/routing";

const EMPTY = "—";

const LOCALE_TAGS: Record<Locale, string> = {
  // arabext digits + persian calendar: an Iranian HR admin reads ۱۴۰۵, not 2026.
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

/**
 * Named separately from formatPercent so the "not scored" case stays explicit:
 * an entity with no confidence must never render as 0%, which is a claim about
 * the model's certainty rather than an absence of one.
 */
export const formatConfidence = formatPercent;
