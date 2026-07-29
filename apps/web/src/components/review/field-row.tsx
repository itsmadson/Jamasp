"use client";

import { useTranslations } from "next-intl";

import { cn } from "@/lib/cn";
import { formatConfidence } from "@/lib/format";
import type { Locale } from "@/i18n/routing";
import type { FieldOut } from "@/lib/api/types";

import { EnumEditor } from "./enum-editor";

const PII_TONES: Record<string, string> = {
  high: "bg-danger/12 text-danger",
  low: "bg-warning/15 text-warning",
  none: "text-muted",
};

const LOW_CONFIDENCE = 0.7;

export function FieldRow({
  field,
  locale,
  onMeaningChange,
  onEnumChange,
}: {
  field: FieldOut;
  locale: string;
  onMeaningChange: (value: string) => void;
  onEnumChange: (code: string, value: string) => void;
}) {
  const t = useTranslations("review");
  const key = locale as Locale;
  const meaning = field.meaning_human?.[key] || field.meaning_ai?.[key] || "";
  const uncertain = field.confidence !== null && field.confidence < LOW_CONFIDENCE;

  return (
    <>
      <tr className={cn("border-b border-border/50", uncertain && "bg-warning/[0.06]")}>
        <td className="px-3 py-2 align-top">
          <span className="identifier text-sm">{field.name}</span>
          {field.is_pk ? <span className="ms-1.5 text-xs text-muted">PK</span> : null}
        </td>
        <td className="px-3 py-2 align-top">
          <span className="identifier text-xs text-muted">{field.data_type}</span>
        </td>
        <td className="px-3 py-2 align-top">
          <input
            aria-label={`${field.name} ${t("meaning")}`}
            value={meaning}
            onChange={(event) => onMeaningChange(event.target.value)}
            className="w-full rounded border border-transparent bg-transparent px-1.5 py-1 text-sm hover:border-border focus-visible:border-accent focus-visible:outline-none"
          />
        </td>
        <td className="px-3 py-2 align-top">
          <span
            className={cn("rounded px-1.5 py-0.5 text-xs", PII_TONES[field.pii_class])}
          >
            {field.pii_class}
          </span>
        </td>
        <td className="px-3 py-2 text-end align-top text-xs text-muted">
          {formatConfidence(field.confidence, locale)}
        </td>
      </tr>

      {field.enum_map ? (
        <tr className="border-b border-border/50">
          <td />
          <td colSpan={4} className="px-3 pb-3">
            <EnumEditor
              enumMap={field.enum_map}
              locale={locale}
              onChange={onEnumChange}
              fieldName={field.name}
            />
          </td>
        </tr>
      ) : null}
    </>
  );
}
