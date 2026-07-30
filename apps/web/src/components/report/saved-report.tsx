"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { ApiError } from "@/lib/api/client";
import { getReport, type Report } from "@/lib/api/reports";

import { BuildProgress } from "./build-progress";
import { ExportButton } from "./export-button";
import { ReportChat } from "./report-chat";
import { ReportView } from "./report-view";

export function SavedReport({ locale, reportId }: { locale: string; reportId: string }) {
  const t = useTranslations("report");
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    getReport(reportId)
      .then(setReport)
      .catch((caught) =>
        setError(caught instanceof ApiError ? caught.detail : t("failed")),
      );
  }, [reportId, t]);

  useEffect(load, [load]);

  if (error) {
    return (
      <p role="alert" className="rounded-md bg-danger/10 px-3 py-2 text-sm text-danger">
        {error}
      </p>
    );
  }

  if (!report) return <p className="text-sm text-muted">…</p>;

  // Opened while the worker is still building it — follow along rather than
  // showing an empty layout that looks like a failure.
  if (report.status === "queued" || report.status === "running") {
    return (
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-4">
        <h1 className="text-2xl font-bold tracking-tight">
          {report.title[locale as "fa" | "en"] || report.title.en}
        </h1>
        <BuildProgress reportId={reportId} locale={locale} onDone={load} />
      </div>
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6">
      <div className="flex justify-end print:hidden">
        <ExportButton />
      </div>

      <ReportView spec={report.spec} datasets={report.datasets} locale={locale} />

      <ReportChat
        reportId={reportId}
        locale={locale}
        className="print:hidden"
        onUpdated={(updated) =>
          // The edit endpoint returns the refreshed rows too, so the page never
          // shows a new layout over stale numbers.
          setReport(updated)
        }
      />


    </div>
  );
}
