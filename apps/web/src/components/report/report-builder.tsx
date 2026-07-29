"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";
import { QueryRefused } from "@/lib/api/query";
import { createReport, listReports, type Report, type ReportSummary } from "@/lib/api/reports";
import { formatDate } from "@/lib/format";
import type { Locale } from "@/i18n/routing";

import { ReportView } from "./report-view";

export function ReportBuilder({ locale, sourceId }: { locale: string; sourceId: string }) {
  const t = useTranslations("report");
  const key = locale as Locale;

  const [question, setQuestion] = useState("");
  const [report, setReport] = useState<Report | null>(null);
  const [saved, setSaved] = useState<ReportSummary[]>([]);
  const [refusal, setRefusal] = useState<{ status: string; message: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    listReports(sourceId).then(setSaved).catch(() => setSaved([]));
  }, [sourceId]);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setReport(null);
    setRefusal(null);
    setError(null);
    setPending(true);
    try {
      const created = await createReport(sourceId, question, locale);
      setReport(created);
      setSaved((current) => [created, ...current]);
    } catch (caught) {
      if (caught instanceof QueryRefused) {
        setRefusal({ status: caught.status, message: caught.message });
      } else {
        setError(caught instanceof ApiError ? caught.detail : t("failed"));
      }
    } finally {
      setPending(false);
    }
  }

  return (
    <section className="mx-auto flex max-w-4xl flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{t("title")}</h1>
      </div>

      <form onSubmit={handleSubmit} className="flex gap-2">
        <input
          aria-label={t("question")}
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder={t("placeholder")}
          className="flex-1 rounded-md border border-border bg-surface px-3 py-2 text-sm outline-none focus-visible:border-accent"
        />
        <Button type="submit" disabled={pending || !question.trim()}>
          {pending ? t("creating") : t("create")}
        </Button>
      </form>

      {error ? (
        <p role="alert" className="rounded-md bg-danger/10 px-3 py-2 text-sm text-danger">
          {error}
        </p>
      ) : null}

      {refusal ? (
        <div role="alert" className="rounded-md bg-warning/10 px-4 py-3 text-sm text-warning">
          <p className="font-medium">{refusal.status}</p>
          <p>{refusal.message}</p>
        </div>
      ) : null}

      {report ? (
        <div className="rounded-lg border border-border bg-background p-6">
          <ReportView
            spec={report.spec}
            columns={report.columns}
            rows={report.rows}
            locale={locale}
          />
        </div>
      ) : null}

      {saved.length > 0 ? (
        <section>
          <h2 className="mb-2 text-sm font-medium text-muted">{t("back")}</h2>
          <ul className="divide-y divide-border rounded-lg border border-border">
            {saved.map((item) => (
              <li key={item.id} className="flex items-center justify-between px-4 py-2.5 text-sm">
                <Link
                  href={`/${locale}/reports/${item.id}`}
                  className="hover:text-accent"
                >
                  {item.title[key] || item.title.en}
                </Link>
                <span className="text-xs text-muted">
                  {formatDate(item.created_at, locale)}
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </section>
  );
}
