"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";
import { QueryRefused } from "@/lib/api/query";
import { editReport, type Report } from "@/lib/api/reports";

interface Turn {
  instruction: string;
  outcome: "applied" | "rejected";
  detail?: string;
}

export function ReportChat({
  reportId,
  locale,
  onUpdated,
  className = "",
}: {
  reportId: string;
  locale: string;
  onUpdated: (report: Report) => void;
  className?: string;
}) {
  const t = useTranslations("report");
  const [instruction, setInstruction] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [pending, setPending] = useState(false);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const asked = instruction.trim();
    if (!asked) return;

    setPending(true);
    setInstruction("");
    try {
      onUpdated(await editReport(reportId, asked, locale));
      setTurns((current) => [...current, { instruction: asked, outcome: "applied" }]);
    } catch (caught) {
      // A rejected edit leaves the report exactly as it was, and the history
      // records that so the user is not left guessing whether it took effect.
      const detail =
        caught instanceof QueryRefused
          ? caught.message
          : caught instanceof ApiError
            ? caught.detail
            : t("failed");
      setTurns((current) => [
        ...current,
        { instruction: asked, outcome: "rejected", detail },
      ]);
    } finally {
      setPending(false);
    }
  }

  return (
    <aside className={`flex flex-col gap-3 rounded-lg border border-border bg-surface p-4 ${className}`}>
      <h2 className="text-sm font-medium">{t("chatTitle")}</h2>

      {turns.length > 0 ? (
        <ul className="flex flex-col gap-2 text-xs">
          {turns.map((turn, index) => (
            <li key={index} className="flex flex-col gap-0.5">
              <span className="text-foreground">{turn.instruction}</span>
              {turn.outcome === "rejected" ? (
                <span className="text-warning">
                  {t("chatRejected")}
                  {turn.detail ? ` — ${turn.detail}` : ""}
                </span>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}

      <form onSubmit={handleSubmit} className="flex gap-2">
        <input
          aria-label={t("chatTitle")}
          value={instruction}
          onChange={(event) => setInstruction(event.target.value)}
          placeholder={t("chatPlaceholder")}
          className="flex-1 rounded-md border border-border bg-background px-3 py-1.5 text-sm outline-none focus-visible:border-accent"
        />
        <Button type="submit" disabled={pending || !instruction.trim()}>
          {pending ? t("chatApplying") : t("chatSend")}
        </Button>
      </form>
    </aside>
  );
}
