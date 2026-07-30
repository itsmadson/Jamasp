"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";
import {
  ask,
  queryHistory,
  QueryRefused,
  type AskResponse,
  type QueryHistoryEntry,
} from "@/lib/api/query";
import { formatDate, formatNumber } from "@/lib/format";
import type { Locale } from "@/i18n/routing";

import { ResultTable } from "./result-table";

interface Refusal {
  status: string;
  message: string;
  sql: string | null;
}

export function AskScreen({ locale, sourceId }: { locale: string; sourceId: string }) {
  const t = useTranslations("ask");
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<AskResponse | null>(null);
  const [refusal, setRefusal] = useState<Refusal | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [history, setHistory] = useState<QueryHistoryEntry[]>([]);

  const reloadHistory = useCallback(() => {
    queryHistory(sourceId).then(setHistory).catch(() => setHistory([]));
  }, [sourceId]);

  useEffect(reloadHistory, [reloadHistory]);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setAnswer(null);
    setRefusal(null);
    setError(null);
    setPending(true);
    try {
      setAnswer(await ask(sourceId, question, locale));
      reloadHistory();
    } catch (caught) {
      if (caught instanceof QueryRefused) {
        // A refusal is a considered outcome, not a crash: show what it declined
        // to do and why.
        setRefusal({ status: caught.status, message: caught.message, sql: caught.sql });
        // A refusal is recorded too — the history is what was asked, not only
        // what succeeded.
        reloadHistory();
      } else {
        setError(caught instanceof ApiError ? caught.detail : t("failed"));
      }
    } finally {
      setPending(false);
    }
  }

  const key = locale as Locale;

  return (
    <section className="mx-auto flex max-w-4xl flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{t("title")}</h1>
        <p className="mt-1 text-sm text-muted">{t("subtitle")}</p>
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
          {pending ? t("asking") : t("ask")}
        </Button>
      </form>

      {error ? (
        <p role="alert" className="rounded-md bg-danger/10 px-3 py-2 text-sm text-danger">
          {error}
        </p>
      ) : null}

      {refusal ? (
        <div
          role="alert"
          className="flex flex-col gap-2 rounded-md bg-warning/10 px-4 py-3 text-sm text-warning"
        >
          <p className="font-medium">{t(`refusal.${refusal.status}`)}</p>
          <p>{refusal.message}</p>
          {refusal.sql ? (
            <pre className="identifier overflow-x-auto rounded bg-background/60 p-2 text-xs">
              {refusal.sql}
            </pre>
          ) : null}
        </div>
      ) : null}

      {answer ? (
        <div className="flex flex-col gap-5">
          <div className="rounded-lg border border-border bg-surface p-4">
            <h2 className="mb-1 text-sm font-medium">{t("explanation")}</h2>
            <p className="text-sm">{answer.explanation[key] || answer.explanation.en}</p>

            {answer.assumptions.length > 0 ? (
              <div className="mt-3 border-t border-border pt-3">
                <h3 className="mb-1 text-xs font-medium text-muted">{t("assumptions")}</h3>
                <ul className="list-inside list-disc text-xs text-muted">
                  {answer.assumptions.map((assumption) => (
                    <li key={assumption}>{assumption}</li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>

          <ResultTable columns={answer.columns} rows={answer.rows} locale={locale} />

          <p className="text-xs text-muted">
            {t("meta", {
              rows: formatNumber(answer.row_count, locale),
              ms: formatNumber(answer.duration_ms, locale),
            })}
          </p>

          <details className="rounded-lg border border-border">
            <summary className="cursor-pointer px-4 py-2 text-sm font-medium">
              {t("sql")}
            </summary>
            <pre className="identifier overflow-x-auto px-4 pb-4 text-xs">{answer.sql}</pre>
          </details>
        </div>
      ) : null}
      {history.length > 0 ? (
        <section className="flex flex-col gap-2">
          <h2 className="text-sm font-medium text-muted">{t("history")}</h2>
          <ul className="divide-y divide-border rounded-lg border border-border">
            {history.map((entry) => (
              <li key={entry.id} className="px-4 py-3">
                <div className="flex items-baseline justify-between gap-3">
                  <button
                    type="button"
                    onClick={() => setQuestion(entry.question)}
                    className="text-start text-sm hover:text-accent"
                    title={t("reuse")}
                  >
                    {entry.question}
                  </button>
                  <span className="shrink-0 text-xs text-muted">
                    {formatDate(entry.created_at, locale)}
                  </span>
                </div>

                <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted">
                  <span
                    className={
                      entry.status === "succeeded" ? "text-accent" : "text-warning"
                    }
                  >
                    {entry.status}
                  </span>
                  {entry.row_count !== null ? (
                    <span>{t("rowsShort", { n: formatNumber(entry.row_count, locale) })}</span>
                  ) : null}
                  {entry.duration_ms !== null ? (
                    <span>{formatNumber(entry.duration_ms, locale)} ms</span>
                  ) : null}
                </div>

                {entry.explanation?.[key] ? (
                  <p className="mt-1 text-xs text-muted">{entry.explanation[key]}</p>
                ) : null}
                {entry.error ? (
                  <p className="mt-1 text-xs text-warning">{entry.error}</p>
                ) : null}
                {entry.sql ? (
                  <details className="mt-1">
                    <summary className="cursor-pointer text-xs text-muted">SQL</summary>
                    <pre className="identifier mt-1 overflow-x-auto text-[11px]">
                      {entry.sql}
                    </pre>
                  </details>
                ) : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </section>
  );
}
