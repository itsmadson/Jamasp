"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { scanEventsUrl, type ScanProgressEvent } from "@/lib/api/scans";

export function ScanProgress({
  scanId,
  onFinished,
}: {
  scanId: string;
  onFinished?: (status: string) => void;
}) {
  const t = useTranslations("scan");
  const [latest, setLatest] = useState<ScanProgressEvent | null>(null);
  const [finalStatus, setFinalStatus] = useState<string | null>(null);
  const [dropped, setDropped] = useState(false);

  useEffect(() => {
    const source = new EventSource(scanEventsUrl(scanId), { withCredentials: true });

    source.onmessage = (event) => {
      const parsed = JSON.parse(event.data) as ScanProgressEvent;
      setLatest(parsed);
      if (parsed.stage === "done") {
        setFinalStatus(parsed.status ?? "succeeded");
        onFinished?.(parsed.status ?? "succeeded");
        source.close();
      }
    };

    // Without this the bar simply freezes and the user waits on nothing.
    source.onerror = () => setDropped(true);

    return () => source.close();
  }, [scanId, onFinished]);

  if (dropped) {
    return (
      <p role="alert" className="rounded-md bg-danger/10 px-3 py-2 text-sm text-danger">
        {t("connectionLost")}
      </p>
    );
  }

  if (finalStatus) {
    return (
      <p className="text-sm">
        {finalStatus === "partial" ? (
          // Partial means some tables have no description; saying "done" would hide that.
          <span className="text-warning">{t("finishedPartial")}</span>
        ) : (
          <span className="text-accent">{t("finishedSucceeded")}</span>
        )}
      </p>
    );
  }

  if (!latest) {
    return <p className="text-sm text-muted">{t("starting")}</p>;
  }

  const showBar = typeof latest.total === "number" && latest.total > 0;

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-baseline justify-between gap-4 text-sm">
        <span className="font-medium">{t(`stage.${latest.stage}`)}</span>
        {latest.message ? (
          <span className="identifier text-xs text-muted">{latest.message}</span>
        ) : null}
      </div>

      {showBar ? (
        <div
          role="progressbar"
          aria-valuenow={latest.current ?? 0}
          aria-valuemin={0}
          aria-valuemax={latest.total}
          className="h-1.5 w-full overflow-hidden rounded-full bg-foreground/10"
        >
          <div
            className="h-full bg-accent transition-[width]"
            style={{ width: `${((latest.current ?? 0) / (latest.total ?? 1)) * 100}%` }}
          />
        </div>
      ) : null}
    </div>
  );
}
