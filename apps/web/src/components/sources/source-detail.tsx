"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/status-badge";
import { ApiError } from "@/lib/api/client";
import { getSource, startScan } from "@/lib/api/sources";
import { formatDate, formatNumber } from "@/lib/format";
import type { ScanOut, SourceOut } from "@/lib/api/types";

import { ScanProgress } from "./scan-progress";

export function SourceDetail({ locale, sourceId }: { locale: string; sourceId: string }) {
  const t = useTranslations("scan");
  const sourcesT = useTranslations("sources");
  const [source, setSource] = useState<SourceOut | null>(null);
  const [activeScan, setActiveScan] = useState<ScanOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  const reload = useCallback(() => {
    getSource(sourceId)
      .then(setSource)
      .catch((caught) =>
        setError(caught instanceof ApiError ? caught.detail : sourcesT("loadFailed")),
      );
  }, [sourceId, sourcesT]);

  useEffect(reload, [reload]);

  async function handleStart() {
    setError(null);
    setStarting(true);
    try {
      setActiveScan(await startScan(sourceId));
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.detail : sourcesT("saveFailed"));
    } finally {
      setStarting(false);
    }
  }

  if (!source) {
    return <p className="text-sm text-muted">{error ?? sourcesT("loading")}</p>;
  }

  return (
    <section className="mx-auto max-w-4xl">
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{source.name}</h1>
          <p className="mt-1 flex items-center gap-2 text-sm text-muted">
            <span className="identifier">{source.kind}</span>
            <StatusBadge status={source.status} />
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link
            href={`/${locale}/sources/${sourceId}/review`}
            className="rounded-md border border-border px-3.5 py-2 text-sm font-medium hover:border-accent"
          >
            {sourcesT("review")}
          </Link>
          <Button onClick={handleStart} disabled={starting} type="button">
            {t("startScan")}
          </Button>
        </div>
      </div>

      {error ? (
        <p role="alert" className="mb-4 rounded-md bg-danger/10 px-3 py-2 text-sm text-danger">
          {error}
        </p>
      ) : null}

      {activeScan ? (
        <div className="mb-6 rounded-lg border border-border bg-surface p-4">
          <ScanProgress scanId={activeScan.id} onFinished={reload} />
        </div>
      ) : null}

      <dl className="grid grid-cols-2 gap-4 text-sm">
        <div>
          <dt className="text-muted">{sourcesT("lastScan")}</dt>
          <dd>
            {source.last_scan_at
              ? formatDate(source.last_scan_at, locale)
              : sourcesT("never")}
          </dd>
        </div>
        <div>
          <dt className="text-muted">{sourcesT("samplingPolicy")}</dt>
          <dd>
            {source.sampling_policy === "masked"
              ? sourcesT("samplingMasked")
              : sourcesT("samplingSchemaOnly")}
          </dd>
        </div>
      </dl>

      {activeScan?.stats ? (
        <p className="mt-4 text-xs text-muted">
          {t("tokens")}: {formatNumber(activeScan.stats.tokens_in ?? 0, locale)} /{" "}
          {formatNumber(activeScan.stats.tokens_out ?? 0, locale)}
        </p>
      ) : null}
    </section>
  );
}
