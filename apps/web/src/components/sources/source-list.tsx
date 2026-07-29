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
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-border text-start text-xs uppercase tracking-wide text-muted">
              <th className="px-3 py-2 text-start font-medium">{t("name")}</th>
              <th className="px-3 py-2 text-start font-medium">{t("kind")}</th>
              <th className="px-3 py-2 text-start font-medium">{t("status")}</th>
              <th className="px-3 py-2 text-start font-medium">{t("lastScan")}</th>
            </tr>
          </thead>
          <tbody>
            {sources.map((source) => (
              <tr key={source.id} className="border-b border-border/60 hover:bg-foreground/[0.03]">
                <td className="px-3 py-3">
                  <Link
                    href={`/${locale}/sources/${source.id}`}
                    className="font-medium hover:text-accent"
                  >
                    {source.name}
                  </Link>
                </td>
                <td className="px-3 py-3 text-muted">
                  <span className="identifier">{source.kind}</span>
                </td>
                <td className="px-3 py-3">
                  <StatusBadge status={source.status} />
                </td>
                <td className="px-3 py-3 text-muted">
                  {source.last_scan_at ? formatDate(source.last_scan_at, locale) : t("never")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <AddSourceDialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        onCreated={(source) => setSources((current) => [...current, source])}
      />
    </section>
  );
}
