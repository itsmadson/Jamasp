"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { ApiError } from "@/lib/api/client";
import { getReport, type Report } from "@/lib/api/reports";

import { ReportChat } from "./report-chat";
import { ReportView } from "./report-view";

export function SavedReport({ locale, reportId }: { locale: string; reportId: string }) {
  const t = useTranslations("report");
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getReport(reportId)
      .then(setReport)
      .catch((caught) =>
        setError(caught instanceof ApiError ? caught.detail : t("failed")),
      );
  }, [reportId, t]);

  if (error) {
    return (
      <p role="alert" className="rounded-md bg-danger/10 px-3 py-2 text-sm text-danger">
        {error}
      </p>
    );
  }

  if (!report) return <p className="text-sm text-muted">…</p>;

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6">
      <ReportView
        spec={report.spec}
        columns={report.columns}
        rows={report.rows}
        locale={locale}
      />

      <ReportChat
        reportId={reportId}
        locale={locale}
        onUpdated={(updated) =>
          // The edit endpoint returns the refreshed rows too, so the page never
          // shows a new layout over stale numbers.
          setReport(updated)
        }
      />

      {report.sql ? (
        <details className="rounded-lg border border-border">
          <summary className="cursor-pointer px-4 py-2 text-sm font-medium">SQL</summary>
          <pre className="identifier overflow-x-auto px-4 pb-4 text-xs">{report.sql}</pre>
        </details>
      ) : null}
    </div>
  );
}
