"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { ApiError } from "@/lib/api/client";
import { getReport, type Report } from "@/lib/api/reports";

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
    <div className="mx-auto max-w-4xl">
      <ReportView
        spec={report.spec}
        columns={report.columns}
        rows={report.rows}
        locale={locale}
      />
      {report.sql ? (
        <details className="mt-6 rounded-lg border border-border">
          <summary className="cursor-pointer px-4 py-2 text-sm font-medium">SQL</summary>
          <pre className="identifier overflow-x-auto px-4 pb-4 text-xs">{report.sql}</pre>
        </details>
      ) : null}
    </div>
  );
}
