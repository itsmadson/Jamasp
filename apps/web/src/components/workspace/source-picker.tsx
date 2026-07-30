"use client";

import { Database, Plus } from "lucide-react";
import { useTranslations } from "next-intl";

import type { SourceOut } from "@/lib/api/types";

/**
 * Which source a question is about.
 *
 * Before, the source was in the URL, so changing it meant navigating away and
 * losing the thread. Here it is a control: the question is about whatever is
 * selected, and that is visible at all times rather than implied by the address bar.
 */
export function SourcePicker({
  sources,
  value,
  onChange,
  locale,
}: {
  sources: SourceOut[];
  value: string;
  onChange: (id: string) => void;
  locale: string;
}) {
  const t = useTranslations("workspace");

  if (sources.length === 0) {
    return (
      <a
        href={`/${locale}/sources`}
        className="flex items-center gap-1.5 rounded-lg border border-dashed border-border px-3 py-1.5 text-sm text-muted hover:border-accent hover:text-foreground"
      >
        <Plus aria-hidden size={15} />
        {t("noSources")}
      </a>
    );
  }

  return (
    <label className="flex items-center gap-2 text-sm">
      <span className="flex items-center gap-1.5 text-muted">
        <Database aria-hidden size={15} />
        {t("source")}
      </span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="rounded-lg border border-border bg-surface px-3 py-1.5 text-sm outline-none focus-visible:border-accent"
      >
        {sources.map((source) => (
          <option key={source.id} value={source.id}>
            {source.name} · {source.kind}
          </option>
        ))}
      </select>
    </label>
  );
}
