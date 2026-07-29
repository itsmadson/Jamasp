"use client";

import { useTranslations } from "next-intl";

import { StatusBadge } from "@/components/ui/status-badge";
import { cn } from "@/lib/cn";
import { formatConfidence } from "@/lib/format";
import type { EntityFilters } from "@/lib/api/entities";
import type { EntitySummaryOut, EntityStatus } from "@/lib/api/types";

const STATUSES: EntityStatus[] = [
  "pending",
  "stale",
  "approved",
  "describe_failed",
  "ignored",
];

interface EntityListProps {
  locale: string;
  entities: EntitySummaryOut[];
  total: number;
  approvedCount: number;
  selectedId: string | null;
  onSelect: (id: string) => void;
  onFilterChange: (filters: EntityFilters) => void;
}

export function EntityList({
  locale,
  entities,
  total,
  approvedCount,
  selectedId,
  onSelect,
  onFilterChange,
}: EntityListProps) {
  const t = useTranslations("review");

  function handleKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    event.preventDefault();

    const index = entities.findIndex((entity) => entity.id === selectedId);
    const next = event.key === "ArrowDown" ? index + 1 : index - 1;
    if (next >= 0 && next < entities.length) onSelect(entities[next].id);
  }

  const progress = total === 0 ? 0 : (approvedCount / total) * 100;

  return (
    <div className="flex h-full flex-col gap-3">
      <div>
        <div className="mb-1.5 flex items-baseline justify-between text-sm">
          <span className="font-medium">{t("progress")}</span>
          <span className="text-muted">
            {approvedCount} / {total}
          </span>
        </div>
        <div className="h-1.5 overflow-hidden rounded-full bg-foreground/10">
          <div className="h-full bg-accent" style={{ width: `${progress}%` }} />
        </div>
      </div>

      <div className="flex flex-col gap-2">
        <input
          type="search"
          aria-label={t("search")}
          placeholder={t("search")}
          onChange={(event) => onFilterChange({ q: event.target.value })}
          className="rounded-md border border-border bg-surface px-3 py-1.5 text-sm"
        />
        <div className="flex gap-2">
          <select
            aria-label={t("status")}
            onChange={(event) =>
              onFilterChange({ status: (event.target.value || undefined) as EntityStatus })
            }
            className="flex-1 rounded-md border border-border bg-surface px-2 py-1.5 text-sm"
          >
            <option value="">{t("allStatuses")}</option>
            {STATUSES.map((status) => (
              <option key={status} value={status}>
                {t(`status.${status}`)}
              </option>
            ))}
          </select>
          <select
            aria-label={t("sort")}
            onChange={(event) =>
              onFilterChange({ sort: event.target.value as EntityFilters["sort"] })
            }
            className="flex-1 rounded-md border border-border bg-surface px-2 py-1.5 text-sm"
          >
            <option value="name">{t("sortName")}</option>
            <option value="confidence_asc">{t("sortConfidence")}</option>
            <option value="status">{t("sortStatus")}</option>
          </select>
        </div>
      </div>

      <div
        role="listbox"
        tabIndex={0}
        aria-label={t("entities")}
        onKeyDown={handleKeyDown}
        className="flex-1 overflow-y-auto rounded-md border border-border outline-none focus-visible:ring-2 focus-visible:ring-accent/30"
      >
        {entities.map((entity) => (
          <div
            key={entity.id}
            role="option"
            aria-selected={entity.id === selectedId}
            onClick={() => onSelect(entity.id)}
            className={cn(
              "flex cursor-pointer items-center justify-between gap-3 border-b border-border/60 px-3 py-2.5 text-sm",
              entity.id === selectedId ? "bg-accent/8" : "hover:bg-foreground/[0.03]",
            )}
          >
            <span className="identifier truncate">{entity.name}</span>
            <span className="flex shrink-0 items-center gap-2">
              <span className="text-xs text-muted">
                {formatConfidence(entity.confidence, locale)}
              </span>
              <StatusBadge status={entity.status} label={t(`status.${entity.status}`)} />
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
