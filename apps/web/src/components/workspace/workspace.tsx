"use client";

import {
  FileChartColumn,
  type LucideIcon,
  Send,
  Sparkles,
  TriangleAlert,
} from "lucide-react";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState } from "react";

import { BuildProgress } from "@/components/report/build-progress";
import { ReportView } from "@/components/report/report-view";
import { ResultTable } from "@/components/query/result-table";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";
import { ask, queryHistory, QueryRefused, type AskResponse } from "@/lib/api/query";
import {
  createReport,
  getReport,
  listReports,
  type Report,
  type ReportSummary,
} from "@/lib/api/reports";
import { listSources } from "@/lib/api/sources";
import type { SourceOut } from "@/lib/api/types";
import { formatDate, formatNumber } from "@/lib/format";
import type { Locale } from "@/i18n/routing";

import { SourcePicker } from "./source-picker";
import { HistoryPanel, type HistoryEntry } from "./history-panel";

type Mode = "answer" | "report";

/** One exchange in the thread. */
interface Turn {
  id: string;
  question: string;
  mode: Mode;
  state: "pending" | "building" | "answered" | "refused" | "failed";
  answer?: AskResponse;
  report?: Report;
  reportId?: string;
  message?: string;
  refusalStatus?: string;
}

let turnCounter = 0;
const nextTurnId = () => `turn-${++turnCounter}`;

/**
 * One place to ask a question, in either shape.
 *
 * The previous flow scattered this across a source page, an ask page and a report
 * page, so the order of operations was something you had to already know. Here the
 * source is a dropdown, asking and reporting are the same composer with a mode, and
 * the work reports its own progress in the thread instead of behind a spinner.
 */
export function Workspace({
  locale,
  initialSourceId,
}: {
  locale: string;
  initialSourceId?: string;
}) {
  const t = useTranslations("workspace");
  const key = locale as Locale;

  const [sources, setSources] = useState<SourceOut[]>([]);
  const [sourceId, setSourceId] = useState<string>(initialSourceId ?? "");
  const [mode, setMode] = useState<Mode>("answer");
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [busy, setBusy] = useState(false);
  const threadEnd = useRef<HTMLDivElement>(null);

  useEffect(() => {
    listSources()
      .then((rows) => {
        setSources(rows);
        setSourceId((current) => current || rows[0]?.id || "");
      })
      .catch(() => setSources([]));
  }, []);

  const reloadHistory = useCallback(() => {
    if (!sourceId) {
      setHistory([]);
      return;
    }
    Promise.all([
      queryHistory(sourceId).catch(() => []),
      listReports(sourceId).catch(() => [] as ReportSummary[]),
    ]).then(([queries, reports]) => {
      const merged: HistoryEntry[] = [
        ...queries.map((row) => ({
          kind: "question" as const,
          id: row.id,
          title: row.question,
          status: row.status,
          created_at: row.created_at,
          rowCount: row.row_count,
        })),
        ...reports.map((row) => ({
          kind: "report" as const,
          id: row.id,
          title: row.title[key] || row.title.en,
          status: "succeeded",
          created_at: row.created_at,
          rowCount: null,
        })),
      ];
      merged.sort((a, b) => b.created_at.localeCompare(a.created_at));
      setHistory(merged);
    });
  }, [sourceId, key]);

  useEffect(reloadHistory, [reloadHistory]);

  useEffect(() => {
    threadEnd.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns]);

  function patch(id: string, changes: Partial<Turn>) {
    setTurns((current) =>
      current.map((turn) => (turn.id === id ? { ...turn, ...changes } : turn)),
    );
  }

  const collectReport = useCallback(
    async (turnId: string, reportId: string) => {
      try {
        const finished = await getReport(reportId);
        patch(turnId, {
          state: finished.status === "failed" ? "failed" : "answered",
          report: finished,
          message: finished.status === "failed" ? t("buildFailed") : undefined,
        });
      } catch (caught) {
        patch(turnId, {
          state: "failed",
          message: caught instanceof ApiError ? caught.detail : t("failed"),
        });
      }
      reloadHistory();
    },
    [reloadHistory, t],
  );

  async function send(event: React.FormEvent) {
    event.preventDefault();
    const text = question.trim();
    if (!text || !sourceId) return;

    const id = nextTurnId();
    setTurns((current) => [...current, { id, question: text, mode, state: "pending" }]);
    setQuestion("");
    setBusy(true);

    try {
      if (mode === "answer") {
        const answer = await ask(sourceId, text, locale);
        patch(id, { state: "answered", answer });
        reloadHistory();
      } else {
        // Returns as soon as the job is queued; the steps arrive on the stream.
        const queued = await createReport(sourceId, text, locale);
        patch(id, { state: "building", reportId: queued.id });
      }
    } catch (caught) {
      if (caught instanceof QueryRefused) {
        patch(id, {
          state: "refused",
          refusalStatus: caught.status,
          message: caught.message,
        });
        reloadHistory();
      } else {
        patch(id, {
          state: "failed",
          message: caught instanceof ApiError ? caught.detail : t("failed"),
        });
      }
    } finally {
      setBusy(false);
    }
  }

  const active = sources.find((source) => source.id === sourceId) ?? null;

  return (
    <div className="flex h-[calc(100dvh-4rem)] gap-4">
      <div className="flex min-w-0 flex-1 flex-col rounded-xl border border-border bg-surface/40">
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3">
          <SourcePicker
            sources={sources}
            value={sourceId}
            onChange={setSourceId}
            locale={locale}
          />
          {active ? (
            <span className="text-xs text-muted">
              {t("askingAbout", { name: active.name })}
            </span>
          ) : null}
        </header>

        <div className="flex-1 overflow-y-auto px-4 py-5">
          {turns.length === 0 ? (
            <EmptyThread locale={locale} onPick={setQuestion} />
          ) : (
            <ol className="flex flex-col gap-6">
              {turns.map((turn) => (
                <li key={turn.id} className="flex flex-col gap-3">
                  <div className="flex justify-end">
                    <p className="max-w-[85%] rounded-2xl bg-accent/12 px-4 py-2 text-sm">
                      {turn.question}
                    </p>
                  </div>

                  {turn.state === "pending" ? (
                    <Thinking label={t(turn.mode === "report" ? "planning" : "thinking")} />
                  ) : null}

                  {turn.state === "building" && turn.reportId ? (
                    <BuildProgress
                      reportId={turn.reportId}
                      locale={locale}
                      onDone={() => collectReport(turn.id, turn.reportId!)}
                    />
                  ) : null}

                  {turn.state === "refused" ? (
                    <div
                      role="alert"
                      className="rounded-lg bg-warning/10 px-4 py-3 text-sm text-warning"
                    >
                      <p className="flex items-center gap-1.5 font-medium">
                        <TriangleAlert aria-hidden size={15} />
                        {t(`refusal.${turn.refusalStatus}`)}
                      </p>
                      <p className="mt-0.5">{turn.message}</p>
                    </div>
                  ) : null}

                  {turn.state === "failed" ? (
                    <p role="alert" className="rounded-lg bg-danger/10 px-4 py-3 text-sm text-danger">
                      {turn.message}
                    </p>
                  ) : null}

                  {turn.answer ? <AnswerCard answer={turn.answer} locale={locale} /> : null}

                  {turn.report ? (
                    <div className="rounded-xl border border-border bg-background p-5">
                      <ReportView
                        spec={turn.report.spec}
                        datasets={turn.report.datasets}
                        locale={locale}
                      />
                    </div>
                  ) : null}
                </li>
              ))}
            </ol>
          )}
          <div ref={threadEnd} />
        </div>

        <form onSubmit={send} className="border-t border-border p-3">
          <div className="mb-2 flex gap-1.5">
            <ModeChip
              active={mode === "answer"}
              onClick={() => setMode("answer")}
              icon={Sparkles}
            >
              {t("modeAnswer")}
            </ModeChip>
            <ModeChip
              active={mode === "report"}
              onClick={() => setMode("report")}
              icon={FileChartColumn}
            >
              {t("modeReport")}
            </ModeChip>
            <span className="self-center ps-1 text-[11px] text-muted">
              {t(mode === "report" ? "modeReportHint" : "modeAnswerHint")}
            </span>
          </div>
          <div className="flex gap-2">
            <input
              aria-label={t("question")}
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder={t(mode === "report" ? "placeholderReport" : "placeholderAsk")}
              disabled={!sourceId}
              className="flex-1 rounded-lg border border-border bg-surface px-3.5 py-2.5 text-sm outline-none focus-visible:border-accent disabled:opacity-50"
            />
            <Button
              type="submit"
              disabled={busy || !question.trim() || !sourceId}
              className="flex items-center gap-1.5"
            >
              {/* Mirrored under RTL, where a paper plane should fly leftward. */}
              <Send aria-hidden size={15} className="rtl:-scale-x-100" />
              {t("send")}
            </Button>
          </div>
        </form>
      </div>

      <HistoryPanel
        entries={history}
        locale={locale}
        onReuse={(entry) => {
          if (entry.kind === "question") setQuestion(entry.title);
        }}
      />
    </div>
  );
}

function ModeChip({
  active,
  onClick,
  icon: Icon,
  children,
}: {
  active: boolean;
  onClick: () => void;
  icon: LucideIcon;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={
        active
          ? "flex items-center gap-1.5 rounded-full bg-accent px-3 py-1 text-xs font-medium text-accent-foreground"
          : "flex items-center gap-1.5 rounded-full border border-border px-3 py-1 text-xs text-muted hover:text-foreground"
      }
    >
      <Icon aria-hidden size={13} />
      {children}
    </button>
  );
}

function Thinking({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-muted">
      <span className="size-2 animate-pulse rounded-full bg-accent" />
      {label}
    </div>
  );
}

function AnswerCard({ answer, locale }: { answer: AskResponse; locale: string }) {
  const t = useTranslations("workspace");
  const key = locale as Locale;

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-border bg-surface p-4">
      <p className="text-sm leading-relaxed">
        {answer.explanation[key] || answer.explanation.en}
      </p>

      <ResultTable columns={answer.columns} rows={answer.rows} locale={locale} />

      <div className="flex flex-wrap items-center gap-3 text-xs text-muted">
        <span>
          {t("meta", {
            rows: formatNumber(answer.row_count, locale),
            ms: formatNumber(answer.duration_ms, locale),
          })}
        </span>
        {answer.tables_used.length > 0 ? (
          <span className="identifier">{answer.tables_used.join(" · ")}</span>
        ) : null}
      </div>

      {answer.assumptions.length > 0 ? (
        <ul className="list-inside list-disc text-xs text-muted">
          {answer.assumptions.map((assumption) => (
            <li key={assumption}>{assumption}</li>
          ))}
        </ul>
      ) : null}

      <details>
        <summary className="cursor-pointer text-xs text-muted">SQL</summary>
        <pre className="identifier mt-1 overflow-x-auto text-[11px]">{answer.sql}</pre>
      </details>
    </div>
  );
}

function EmptyThread({
  locale,
  onPick,
}: {
  locale: string;
  onPick: (text: string) => void;
}) {
  const t = useTranslations("workspace");
  const examples = [t("example1"), t("example2"), t("example3")];

  return (
    <div className="mx-auto flex max-w-lg flex-col items-center gap-4 py-16 text-center">
      <h2 className="text-lg font-medium">{t("emptyTitle")}</h2>
      <p className="text-sm text-muted">{t("emptyBody")}</p>
      <ul className="flex w-full flex-col gap-2">
        {examples.map((example) => (
          <li key={example}>
            <button
              type="button"
              onClick={() => onPick(example)}
              className="w-full rounded-lg border border-border px-4 py-2.5 text-start text-sm text-muted transition-colors hover:border-accent hover:text-foreground"
            >
              {example}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

export { formatDate };
