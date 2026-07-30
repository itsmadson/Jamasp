"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/status-badge";
import { ApiError } from "@/lib/api/client";
import { listSources } from "@/lib/api/sources";
import { formatDate } from "@/lib/format";
import type { SourceOut } from "@/lib/api/types";

import { AddSourceDialog } from "./add-source-dialog";

export function SourceList({ locale }: { locale: string }) {
  const t = useTranslations("sources");
  const [sources, setSources] = useState<SourceOut[]>([]);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listSources()
      .then(setSources)
      .catch((caught) =>
        setError(caught instanceof ApiError ? caught.detail : t("loadFailed")),
      )
      .finally(() => setLoading(false));
  }, [t]);

  return (
    <section className="mx-auto max-w-5xl">
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{t("title")}</h1>
          <p className="mt-1 text-sm text-muted">{t("subtitle")}</p>
        </div>
        <Button onClick={() => setDialogOpen(true)} type="button">
          {t("addSource")}
        </Button>
      </div>

      {error ? (
        <p role="alert" className="mb-4 rounded-md bg-danger/10 px-3 py-2 text-sm text-danger">
          {error}
        </p>
      ) : null}

      {loading ? (
        <p className="px-3 py-12 text-center text-sm text-muted">{t("loading")}</p>
      ) : sources.length === 0 ? (
        <p className="rounded-lg border border-dashed border-border px-6 py-12 text-center text-sm text-muted">
          {t("empty")}
        </p>
      ) : (
        <ul className="flex flex-col gap-2">
          {sources.map((source) => (
            <li key={source.id}>
              {/* The whole card is the target. A four-character name was the only
                  way forward before, which is not a control anyone can find. */}
              <Link
                href={`/${locale}/sources/${source.id}`}
                className="flex items-center justify-between gap-4 rounded-lg border border-border bg-surface px-4 py-3.5 transition-colors hover:border-accent"
              >
                <div className="flex flex-col gap-1">
                  <span className="text-base font-medium">{source.name}</span>
                  <span className="flex items-center gap-2 text-xs text-muted">
                    <span className="identifier">{source.kind}</span>
                    <span>·</span>
                    <span>
                      {t("lastScan")}:{" "}
                      {source.last_scan_at
                        ? formatDate(source.last_scan_at, locale)
                        : t("never")}
                    </span>
                  </span>
                </div>

                <div className="flex items-center gap-3">
                  <StatusBadge status={source.status} />
                  <span className="text-sm font-medium text-accent">
                    {source.status === "draft" ? t("startHere") : t("open")}
                  </span>
                  <span aria-hidden="true" className="text-muted rtl:rotate-180">
                    →
                  </span>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}

      <AddSourceDialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        onCreated={(source) => setSources((current) => [...current, source])}
      />
    </section>
  );
}
