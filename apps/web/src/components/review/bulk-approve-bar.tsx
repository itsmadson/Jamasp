"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { ApiError } from "@/lib/api/client";
import { bulkApprove } from "@/lib/api/entities";

const THRESHOLDS = [0.9, 0.8, 0.7];

export function BulkApproveBar({
  pendingCount,
  sourceId,
  onApproved,
}: {
  pendingCount: number;
  sourceId: string;
  onApproved: () => void;
}) {
  const t = useTranslations("bulk");
  const common = useTranslations("common");
  const [threshold, setThreshold] = useState(0.8);
  const [confirming, setConfirming] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function confirm() {
    setError(null);
    setPending(true);
    try {
      await bulkApprove(sourceId, threshold);
      setConfirming(false);
      onApproved();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.detail : t("failed"));
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="rounded-md border border-border bg-surface p-3">
      <div className="flex items-center gap-2">
        <select
          aria-label={t("threshold")}
          value={threshold}
          onChange={(event) => setThreshold(Number(event.target.value))}
          className="rounded border border-border bg-background px-2 py-1 text-xs"
        >
          {THRESHOLDS.map((value) => (
            <option key={value} value={value}>
              ≥ {Math.round(value * 100)}%
            </option>
          ))}
        </select>
        <Button
          variant="secondary"
          type="button"
          className="flex-1 text-xs"
          onClick={() => setConfirming(true)}
        >
          {t("approveAll")}
        </Button>
      </div>

      <Dialog
        open={confirming}
        onClose={() => setConfirming(false)}
        title={t("confirmTitle")}
        footer={
          <>
            <Button variant="secondary" type="button" onClick={() => setConfirming(false)}>
              {common("cancel")}
            </Button>
            <Button type="button" onClick={confirm} disabled={pending}>
              {t("confirm")}
            </Button>
          </>
        }
      >
        <p className="text-sm">
          {t("confirmBody", {
            count: pendingCount,
            threshold: Math.round(threshold * 100),
          })}
        </p>
        <p className="mt-2 text-xs text-muted">{t("confirmWarning")}</p>
        {error ? (
          <p role="alert" className="mt-3 rounded bg-danger/10 px-3 py-2 text-sm text-danger">
            {error}
          </p>
        ) : null}
      </Dialog>
    </div>
  );
}
