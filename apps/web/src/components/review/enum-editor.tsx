"use client";

import type { Locale } from "@/i18n/routing";
import type { Bilingual } from "@/lib/api/types";

/**
 * Where a reviewer fixes the model guessing that status = 3 means "cancelled"
 * when the business means "rejected". Getting this wrong silently corrupts
 * every future report that filters on the column.
 */
export function EnumEditor({
  enumMap,
  locale,
  fieldName,
  onChange,
}: {
  enumMap: Record<string, Bilingual>;
  locale: string;
  fieldName: string;
  onChange: (code: string, value: string) => void;
}) {
  const key = locale as Locale;

  return (
    <div className="flex flex-wrap gap-2">
      {Object.entries(enumMap).map(([code, label]) => (
        <div
          key={code}
          className="flex items-center gap-1.5 rounded border border-border bg-background px-2 py-1"
        >
          <span className="identifier text-xs text-muted">{code}</span>
          <span aria-hidden="true" className="text-muted">
            →
          </span>
          <input
            aria-label={`${fieldName} ${code}`}
            value={label[key] ?? ""}
            onChange={(event) => onChange(code, event.target.value)}
            className="w-28 bg-transparent text-xs outline-none focus-visible:underline"
          />
        </div>
      ))}
    </div>
  );
}
