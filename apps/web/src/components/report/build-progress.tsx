"use client";

import {
  Check,
  Circle,
  FileChartColumn,
  ListTree,
  Loader,
  type LucideIcon,
} from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";

import { reportEventsUrl, type ReportProgressEvent, type ReportStage } from "@/lib/api/reports";

/** The stages a build passes through, in order. */
const STAGES: ReportStage[] = ["plan", "query", "design"];

const STAGE_ICONS: Record<string, LucideIcon> = {
  plan: ListTree,
  query: Loader,
  design: FileChartColumn,
};

interface Step {
  stage: ReportStage;
  message: string;
  current?: number;
  total?: number;
}

/**
 * Follows a report build and shows what it is doing.
 *
 * A build is several model calls, so the honest thing during the wait is to say
 * which step is running — not to spin silently until a proxy gives up and the user
 * concludes it crashed.
 */
export function BuildProgress({
  reportId,
  locale,
  onDone,
}: {
  reportId: string;
  locale: string;
  onDone: (status: string) => void;
}) {
  const t = useTranslations("report");
  const [steps, setSteps] = useState<Step[]>([]);
  const [stage, setStage] = useState<ReportStage>("plan");
  const settled = useRef(false);

  useEffect(() => {
    const source = new EventSource(reportEventsUrl(reportId));

    source.onmessage = (event) => {
      const payload = JSON.parse(event.data) as ReportProgressEvent;

      if (payload.stage === "done") {
        settled.current = true;
        source.close();
        onDone(payload.status ?? "succeeded");
        return;
      }
      if (payload.stage === "status") return;

      setStage(payload.stage);
      setSteps((current) => [
        ...current,
        {
          stage: payload.stage,
          message: payload.message ?? "",
          current: payload.current,
          total: payload.total,
        },
      ]);
    };

    source.onerror = () => {
      // The stream dropping is not the build failing. The build runs in a worker,
      // so the page falls back to asking for the finished report.
      source.close();
      if (!settled.current) onDone("unknown");
    };

    return () => source.close();
  }, [reportId, onDone]);

  const reached = STAGES.indexOf(stage);

  return (
    <div className="flex flex-col gap-4 rounded-lg border border-border bg-surface p-5">
      <ol className="flex flex-col gap-3">
        {STAGES.map((name, index) => {
          const done = index < reached;
          const active = index === reached;
          const latest = [...steps].reverse().find((step) => step.stage === name);
          const Pending = STAGE_ICONS[name] ?? Circle;

          return (
            <li key={name} className="flex items-start gap-3">
              {done ? (
                <Check aria-hidden size={16} className="mt-0.5 shrink-0 text-accent" />
              ) : active ? (
                <Loader
                  aria-hidden
                  size={16}
                  className="mt-0.5 shrink-0 animate-spin text-accent"
                />
              ) : (
                // Its own glyph rather than a blank circle, so a step still to come
                // says what it will do.
                <Pending aria-hidden size={16} className="mt-0.5 shrink-0 text-muted/40" />
              )}
              <div className="flex min-w-0 flex-col">
                <span
                  className={
                    active || done ? "text-sm font-medium" : "text-sm text-muted"
                  }
                >
                  {t(`stage.${name}`)}
                  {latest?.total && latest.total > 1
                    ? ` (${latest.current ?? 0}/${latest.total})`
                    : ""}
                </span>
                {latest?.message ? (
                  <span className="truncate text-xs text-muted" title={latest.message}>
                    {latest.message}
                  </span>
                ) : null}
              </div>
            </li>
          );
        })}
      </ol>

      <p className="text-xs text-muted">{t("keepsRunning")}</p>
    </div>
  );
}
