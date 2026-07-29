"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/status-badge";
import { ApiError } from "@/lib/api/client";
import {
  approveEntity,
  ignoreEntity,
  patchEntity,
  type FieldPatch,
} from "@/lib/api/entities";
import { formatConfidence, formatNumber } from "@/lib/format";
import type { Locale } from "@/i18n/routing";
import type { Bilingual, EntityOut } from "@/lib/api/types";

import { FieldRow } from "./field-row";

function otherLocale(locale: string): Locale {
  return locale === "fa" ? "en" : "fa";
}

export function EntityCard({
  entity,
  locale,
  onChanged,
  onApproved,
}: {
  entity: EntityOut;
  locale: string;
  onChanged: (entity: EntityOut) => void;
  onApproved: () => void;
}) {
  const t = useTranslations("review");
  const common = useTranslations("common");
  const key = locale as Locale;

  const aiSummary = entity.description_ai?.summary?.[key] ?? "";
  const humanSummary = entity.description_human?.summary?.[key] ?? "";
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(humanSummary || aiSummary);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function save(patch: Parameters<typeof patchEntity>[1]) {
    setError(null);
    setPending(true);
    try {
      onChanged(await patchEntity(entity.id, patch));
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.detail : t("saveFailed"));
    } finally {
      setPending(false);
    }
  }

  async function saveSummary() {
    const other = otherLocale(locale);
    // Carry the other language through untouched: editing English must not
    // blank the Persian summary a colleague wrote.
    const summary = {
      [key]: draft,
      [other]:
        entity.description_human?.summary?.[other] ??
        entity.description_ai?.summary?.[other] ??
        "",
    } as Bilingual;

    await save({ description_human: { ...entity.description_human, summary } });
    setEditing(false);
  }

  function patchField(fieldId: string, changes: Omit<FieldPatch, "id">) {
    void save({ fields: [{ id: fieldId, ...changes }] });
  }

  async function handleApprove() {
    setError(null);
    setPending(true);
    try {
      await approveEntity(entity.id);
      onApproved();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.detail : t("saveFailed"));
    } finally {
      setPending(false);
    }
  }

  const failed = entity.status === "describe_failed";

  return (
    <article className="flex flex-col gap-5">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h2 className="identifier text-xl font-bold">
            {entity.schema_name}.{entity.name}
          </h2>
          <p className="mt-1 flex items-center gap-2 text-xs text-muted">
            <span>{entity.kind}</span>
            {entity.row_count_approx !== null ? (
              <span>
                {formatNumber(entity.row_count_approx, locale)} {t("rows")}
              </span>
            ) : null}
            <span>
              {t("confidence")}: {formatConfidence(entity.confidence, locale)}
            </span>
          </p>
        </div>
        <StatusBadge status={entity.status} label={t(`status.${entity.status}`)} />
      </header>

      {entity.status === "stale" ? (
        <p className="rounded-md bg-warning/10 px-3 py-2 text-sm text-warning">
          {t("staleBanner")}
        </p>
      ) : null}
      {failed ? (
        <p className="rounded-md bg-danger/10 px-3 py-2 text-sm text-danger">
          {t("failedBanner")}
        </p>
      ) : null}

      <section>
        <div className="mb-1.5 flex items-center justify-between">
          <h3 className="text-sm font-medium">{t("summary")}</h3>
          {!editing && !failed ? (
            <Button variant="ghost" type="button" onClick={() => setEditing(true)}>
              {t("editSummary")}
            </Button>
          ) : null}
        </div>

        {editing ? (
          <div className="flex flex-col gap-2">
            <textarea
              aria-label={t("summary")}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              rows={3}
              className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm"
            />
            <div className="flex justify-end gap-2">
              <Button variant="secondary" type="button" onClick={() => setEditing(false)}>
                {common("cancel")}
              </Button>
              <Button type="button" onClick={saveSummary} disabled={pending}>
                {common("save")}
              </Button>
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            {humanSummary ? <p className="text-sm">{humanSummary}</p> : null}
            {aiSummary ? (
              <p className={humanSummary ? "text-xs text-muted" : "text-sm"}>
                {humanSummary ? (
                  <span className="me-1.5 rounded bg-foreground/8 px-1.5 py-0.5">
                    {t("aiSuggested")}
                  </span>
                ) : null}
                {aiSummary}
              </p>
            ) : null}
          </div>
        )}

        {entity.description_ai?.grain ? (
          <p className="mt-2 text-xs text-muted">
            {t("grain")}: {entity.description_ai.grain}
          </p>
        ) : null}
      </section>

      <section>
        <h3 className="mb-1.5 text-sm font-medium">{t("columns")}</h3>
        <table className="w-full border-collapse">
          <thead>
            <tr className="border-b border-border text-xs uppercase tracking-wide text-muted">
              <th className="px-3 py-1.5 text-start font-medium">{t("column")}</th>
              <th className="px-3 py-1.5 text-start font-medium">{t("type")}</th>
              <th className="px-3 py-1.5 text-start font-medium">{t("meaning")}</th>
              <th className="px-3 py-1.5 text-start font-medium">{t("pii")}</th>
              <th className="px-3 py-1.5 text-end font-medium">{t("confidence")}</th>
            </tr>
          </thead>
          <tbody>
            {entity.fields.map((field) => (
              <FieldRow
                key={field.id}
                field={field}
                locale={locale}
                onMeaningChange={(value) =>
                  patchField(field.id, {
                    meaning_human: {
                      [key]: value,
                      [otherLocale(locale)]:
                        field.meaning_human?.[otherLocale(locale)] ??
                        field.meaning_ai?.[otherLocale(locale)] ??
                        "",
                    } as Bilingual,
                  })
                }
                onEnumChange={(code, value) =>
                  patchField(field.id, {
                    enum_map: {
                      ...field.enum_map,
                      [code]: {
                        ...(field.enum_map?.[code] ?? { fa: "", en: "" }),
                        [key]: value,
                      },
                    } as Record<string, Bilingual>,
                  })
                }
              />
            ))}
          </tbody>
        </table>
      </section>

      {error ? (
        <p role="alert" className="rounded-md bg-danger/10 px-3 py-2 text-sm text-danger">
          {error}
        </p>
      ) : null}

      <footer className="flex justify-end gap-2 border-t border-border pt-4">
        <Button
          variant="ghost"
          type="button"
          onClick={async () => {
            await ignoreEntity(entity.id);
            onApproved();
          }}
        >
          {t("ignore")}
        </Button>
        {failed ? (
          <Button type="button" onClick={onApproved}>
            {t("retry")}
          </Button>
        ) : (
          <Button type="button" onClick={handleApprove} disabled={pending}>
            {t("approve")}
          </Button>
        )}
      </footer>
    </article>
  );
}
