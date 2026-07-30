"use client";

import {
  ChevronRight,
  Database,
  FileChartColumn,
  ListChecks,
  type LucideIcon,
  MessageCircleQuestion,
  MessagesSquare,
  Plus,
  RefreshCw,
  ScanSearch,
  Table2,
  TriangleAlert,
} from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useEffect, useState } from "react";

import { getOverview, type Overview, type SourceProgress } from "@/lib/api/overview";
import { formatDate, formatNumber } from "@/lib/format";

const STEPS = [
  { key: "scan", icon: ScanSearch },
  { key: "review", icon: ListChecks },
  { key: "ask", icon: MessageCircleQuestion },
] as const;

// One glyph per state, so the button is recognisable before it is read.
const ACTION_ICONS: Record<SourceProgress["next_step"], LucideIcon> = {
  scan: ScanSearch,
  scanning: RefreshCw,
  review: ListChecks,
  ask: MessageCircleQuestion,
  ready: MessagesSquare,
};

/**
 * What is set up, what needs attention, and what to do next.
 *
 * The product has a real order to it — connect, scan, review, then ask — and
 * nothing in the old UI said so, which is why the workflow was not obvious. Each
 * source shows the one action it is actually waiting for.
 */
export function Dashboard({ locale }: { locale: string }) {
  const t = useTranslations("dashboard");
  const [overview, setOverview] = useState<Overview | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await getOverview();
        if (!cancelled) setOverview(data);
      } catch {
        if (!cancelled) setError(true);
      }
    })();
    // The flag stops a slow response writing into a component that is gone.
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) {
    return (
      <p role="alert" className="rounded-lg bg-danger/10 px-4 py-3 text-sm text-danger">
        {t("failed")}
      </p>
    );
  }
  if (!overview) return <p className="text-sm text-muted">…</p>;

  const { totals, sources, recent } = overview;
  const needsAttention = sources.filter(
    (source) => source.next_step === "review" || source.next_step === "scan",
  );

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-8">
      <header>
        <h1 className="text-2xl font-bold tracking-tight">{t("title")}</h1>
        <p className="mt-1 text-sm text-muted">{t("subtitle")}</p>
      </header>

      {sources.length === 0 ? (
        <FirstRun locale={locale} />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat
              icon={Database}
              label={t("stat.sources")}
              value={totals.sources}
              locale={locale}
            />
            <Stat
              icon={Table2}
              label={t("stat.tables")}
              value={totals.entities}
              locale={locale}
            />
            <Stat
              icon={ListChecks}
              label={t("stat.pending")}
              value={totals.pending}
              locale={locale}
              tone={totals.pending > 0 ? "warning" : "plain"}
            />
            <Stat
              icon={FileChartColumn}
              label={t("stat.reports")}
              value={totals.reports}
              locale={locale}
            />
          </div>

          {needsAttention.length > 0 ? (
            <section className="flex flex-col gap-2">
              <h2 className="flex items-center gap-1.5 text-sm font-medium">
                <TriangleAlert aria-hidden size={15} className="text-warning" />
                {t("attention")}
              </h2>
              <ul className="flex flex-col gap-2">
                {needsAttention.map((source) => (
                  <SourceRow key={source.id} source={source} locale={locale} />
                ))}
              </ul>
            </section>
          ) : null}

          <section className="flex flex-col gap-2">
            <div className="flex items-baseline justify-between">
              <h2 className="text-sm font-medium">{t("allSources")}</h2>
              <Link
                href={`/${locale}/sources`}
                className="text-xs text-muted hover:text-accent"
              >
                {t("manage")}
              </Link>
            </div>
            <ul className="flex flex-col gap-2">
              {sources.map((source) => (
                <SourceRow key={source.id} source={source} locale={locale} />
              ))}
            </ul>
          </section>

          {recent.length > 0 ? (
            <section className="flex flex-col gap-2">
              <h2 className="text-sm font-medium">{t("recent")}</h2>
              <ul className="divide-y divide-border rounded-xl border border-border">
                {recent.map((item) => (
                  <li
                    key={`${item.kind}-${item.id}`}
                    className="flex items-center gap-3 px-4 py-2.5 text-sm"
                  >
                    <span
                      className={
                        item.kind === "report"
                          ? "flex items-center gap-1 rounded bg-accent/12 px-1.5 py-0.5 text-[10px] text-accent"
                          : "flex items-center gap-1 rounded bg-border/60 px-1.5 py-0.5 text-[10px] text-muted"
                      }
                    >
                      {item.kind === "report" ? (
                        <FileChartColumn aria-hidden size={11} />
                      ) : (
                        <MessageCircleQuestion aria-hidden size={11} />
                      )}
                      {t(`kind.${item.kind}`)}
                    </span>
                    {item.kind === "report" ? (
                      <Link
                        href={`/${locale}/reports/${item.id}`}
                        className="min-w-0 flex-1 truncate hover:text-accent"
                      >
                        {item.title}
                      </Link>
                    ) : (
                      <span className="min-w-0 flex-1 truncate">{item.title}</span>
                    )}
                    <span className="shrink-0 text-xs text-muted">
                      {formatDate(item.created_at, locale)}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
        </>
      )}
    </div>
  );
}

function Stat({
  icon: Icon,
  label,
  value,
  locale,
  tone = "plain",
}: {
  icon: LucideIcon;
  label: string;
  value: number;
  locale: string;
  tone?: "plain" | "warning";
}) {
  return (
    <div className="rounded-xl border border-border bg-surface p-4">
      <p className="flex items-center gap-1.5 text-xs text-muted">
        <Icon aria-hidden size={14} />
        {label}
      </p>
      <p
        className={`mt-1 text-2xl font-semibold tabular-nums ${
          tone === "warning" && value > 0 ? "text-warning" : ""
        }`}
      >
        {formatNumber(value ?? 0, locale)}
      </p>
    </div>
  );
}

function SourceRow({ source, locale }: { source: SourceProgress; locale: string }) {
  const t = useTranslations("dashboard");

  const reached =
    source.next_step === "scan" || source.next_step === "scanning"
      ? 0
      : source.next_step === "review"
        ? 1
        : 2;

  const ActionIcon = ACTION_ICONS[source.next_step];
  const href =
    source.next_step === "review"
      ? `/${locale}/sources/${source.id}/review`
      : source.next_step === "scan" || source.next_step === "scanning"
        ? `/${locale}/sources/${source.id}`
        : `/${locale}/workspace?source=${source.id}`;

  return (
    <li className="rounded-xl border border-border bg-surface p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <Link
            href={`/${locale}/sources/${source.id}`}
            className="font-medium hover:text-accent"
          >
            {source.name}
          </Link>
          <span className="ms-2 text-xs text-muted">{source.kind}</span>
        </div>

        <Link
          href={href}
          className="flex items-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-accent-foreground hover:opacity-90"
        >
          <ActionIcon
            aria-hidden
            size={14}
            className={source.next_step === "scanning" ? "animate-spin" : undefined}
          />
          {t(`action.${source.next_step}`)}
          {/* Flipped under RTL, where forward is leftward. */}
          <ChevronRight aria-hidden size={14} className="rtl:-scale-x-100" />
        </Link>
      </div>

      {/* The journey, so the order of operations is visible rather than assumed. */}
      <ol className="mt-3 flex items-center gap-2">
        {STEPS.map((step, index) => (
          <li key={step.key} className="flex flex-1 items-center gap-2">
            <step.icon
              aria-hidden
              size={14}
              className={
                index < reached
                  ? "shrink-0 text-accent"
                  : index === reached
                    ? "shrink-0 text-accent"
                    : "shrink-0 text-muted/50"
              }
            />
            <span
              className={`text-[11px] ${index <= reached ? "text-foreground" : "text-muted"}`}
            >
              {t(`step.${step.key}`)}
            </span>
            {index < STEPS.length - 1 ? (
              <span
                className={`h-px flex-1 ${index < reached ? "bg-accent/40" : "bg-border"}`}
              />
            ) : null}
          </li>
        ))}
      </ol>

      <div className="mt-3 flex flex-wrap gap-4 text-xs text-muted">
        <span>{t("tables", { n: formatNumber(source.entities_total, locale) })}</span>
        <span>{t("approved", { n: formatNumber(source.entities_approved, locale) })}</span>
        {source.entities_pending > 0 ? (
          <span className="text-warning">
            {t("awaiting", { n: formatNumber(source.entities_pending, locale) })}
          </span>
        ) : null}
        {source.last_scan_at ? (
          <span className="ms-auto">
            {t("lastScan", { when: formatDate(source.last_scan_at, locale) })}
          </span>
        ) : null}
      </div>
    </li>
  );
}

function FirstRun({ locale }: { locale: string }) {
  const t = useTranslations("dashboard");
  return (
    <section className="rounded-xl border border-dashed border-border p-8 text-center">
      <h2 className="text-lg font-medium">{t("firstRunTitle")}</h2>
      <p className="mx-auto mt-2 max-w-md text-sm text-muted">{t("firstRunBody")}</p>
      <Link
        href={`/${locale}/sources`}
        className="mt-5 inline-flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-foreground hover:opacity-90"
      >
        <Plus aria-hidden size={16} />
        {t("firstRunAction")}
      </Link>
    </section>
  );
}
