"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { ApiError } from "@/lib/api/client";
import {
  getEntity,
  listEntities,
  type EntityFilters,
} from "@/lib/api/entities";
import type { EntityOut, EntitySummaryOut } from "@/lib/api/types";

import { BulkApproveBar } from "./bulk-approve-bar";
import { EntityCard } from "./entity-card";
import { EntityList } from "./entity-list";

export function ReviewScreen({ locale, sourceId }: { locale: string; sourceId: string }) {
  const t = useTranslations("review");
  const [filters, setFilters] = useState<EntityFilters>({ sort: "name", limit: 200 });
  const [entities, setEntities] = useState<EntitySummaryOut[]>([]);
  const [total, setTotal] = useState(0);
  const [approvedCount, setApprovedCount] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selected, setSelected] = useState<EntityOut | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [listed, approved] = await Promise.all([
        listEntities(sourceId, filters),
        listEntities(sourceId, { status: "approved", limit: 1 }),
      ]);
      setEntities(listed.items);
      setTotal(listed.total);
      setApprovedCount(approved.total);
      setSelectedId((current) => current ?? listed.items[0]?.id ?? null);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.detail : t("loadFailed"));
    }
  }, [sourceId, filters, t]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!selectedId) return;
    getEntity(selectedId)
      .then(setSelected)
      .catch((caught) =>
        setError(caught instanceof ApiError ? caught.detail : t("loadFailed")),
      );
  }, [selectedId, t]);

  function selectNext() {
    const index = entities.findIndex((entity) => entity.id === selectedId);
    const next = entities[index + 1];
    setSelectedId(next ? next.id : null);
    void refresh();
  }

  return (
    <div className="mx-auto flex h-[calc(100dvh-8rem)] max-w-7xl gap-6">
      <aside className="flex w-80 shrink-0 flex-col gap-3">
        <EntityList
          locale={locale}
          entities={entities}
          total={total}
          approvedCount={approvedCount}
          selectedId={selectedId}
          onSelect={setSelectedId}
          onFilterChange={(next) => setFilters((current) => ({ ...current, ...next }))}
        />
        <BulkApproveBar
          pendingCount={total - approvedCount}
          sourceId={sourceId}
          onApproved={refresh}
        />
      </aside>

      <section className="flex-1 overflow-y-auto rounded-lg border border-border bg-surface p-6">
        {error ? (
          <p role="alert" className="rounded-md bg-danger/10 px-3 py-2 text-sm text-danger">
            {error}
          </p>
        ) : selected ? (
          <EntityCard
            entity={selected}
            locale={locale}
            onChanged={setSelected}
            onApproved={selectNext}
          />
        ) : (
          <p className="text-sm text-muted">{t("selectPrompt")}</p>
        )}
      </section>
    </div>
  );
}
