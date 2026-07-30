"use client";

import { FileChartColumn, History, MessageCircleQuestion } from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useState } from "react";

import { formatDate, formatNumber } from "@/lib/format";

export interface HistoryEntry {
  kind: "question" | "report";
  id: string;
  title: string;
  status: string;
  created_at: string;
  rowCount: number | null;
}

/**
 * Everything ever asked of this source.
 *
 * Both kinds share one list because from the user's side they are the same act —
 * a question they asked — and splitting them into separate pages is what made the
 * work feel like it disappeared.
 */
export function HistoryPanel({
  entries,
  locale,
  onReuse,
}: {
  entries: HistoryEntry[];
  locale: string;
  onReuse: (entry: HistoryEntry) => void;
}) {
  const t = useTranslations("workspace");
  const [filter, setFilter] = useState<"all" | "question" | "report">("all");

  const shown = entries.filter((entry) => filter === "all" || entry.kind === filter);

  return (
    <aside className="hidden w-72 shrink-0 flex-col rounded-xl border border-border bg-surface/40 lg:flex">
      <header className="border-b border-border px-4 py-3">
        <h2 className="mb-2 flex items-center gap-1.5 text-sm font-medium">
          <History aria-hidden size={15} />
          {t("history")}
        </h2>
        <div className="flex gap-1">
          {(["all", "question", "report"] as const).map((value) => (
            <button
              key={value}
              type="button"
              onClick={() => setFilter(value)}
              aria-pressed={filter === value}
              className={
                filter === value
                  ? "rounded-full bg-accent/15 px-2.5 py-0.5 text-[11px] font-medium text-accent"
                  : "rounded-full px-2.5 py-0.5 text-[11px] text-muted hover:text-foreground"
              }
            >
              {t(`filter.${value}`)}
            </button>
          ))}
        </div>
      </header>

      <div className="flex-1 overflow-y-auto">
        {shown.length === 0 ? (
          <p className="px-4 py-6 text-xs text-muted">{t("historyEmpty")}</p>
        ) : (
          <ul className="divide-y divide-border">
            {shown.map((entry) => (
              <li key={`${entry.kind}-${entry.id}`} className="px-4 py-2.5">
                {entry.kind === "report" ? (
                  <Link
                    href={`/${locale}/reports/${entry.id}`}
                    className="line-clamp-2 text-xs hover:text-accent"
                  >
                    {entry.title}
                  </Link>
                ) : (
                  <button
                    type="button"
                    onClick={() => onReuse(entry)}
                    title={t("reuse")}
                    className="line-clamp-2 text-start text-xs hover:text-accent"
                  >
                    {entry.title}
                  </button>
                )}

                <div className="mt-1 flex items-center gap-2 text-[10px] text-muted">
                  <span
                    className={
                      entry.kind === "report"
                        ? "flex items-center gap-1 rounded bg-accent/12 px-1.5 py-0.5 text-accent"
                        : "flex items-center gap-1 rounded bg-border/60 px-1.5 py-0.5"
                    }
                  >
                    {entry.kind === "report" ? (
                      <FileChartColumn aria-hidden size={10} />
                    ) : (
                      <MessageCircleQuestion aria-hidden size={10} />
                    )}
                    {t(`kind.${entry.kind}`)}
                  </span>
                  {entry.rowCount !== null ? (
                    <span>{t("rows", { n: formatNumber(entry.rowCount, locale) })}</span>
                  ) : null}
                  <span className="ms-auto">{formatDate(entry.created_at, locale)}</span>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </aside>
  );
}
