"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import type { RouteConfig } from "@/lib/api/settings";

export function RouteTable({
  routes,
  providers,
  onSave,
}: {
  routes: Record<string, RouteConfig>;
  providers: string[];
  onSave: (changed: Record<string, RouteConfig>) => void;
}) {
  const t = useTranslations("settings");
  const [draft, setDraft] = useState(routes);

  function update(task: string, changes: Partial<RouteConfig>) {
    setDraft((current) => ({ ...current, [task]: { ...current[task], ...changes } }));
  }

  function handleSave() {
    // Send only what actually differs, so an untouched route is never rewritten
    // with values the admin never looked at.
    const changed = Object.fromEntries(
      Object.entries(draft).filter(
        ([task, route]) =>
          route.provider !== routes[task].provider ||
          route.model !== routes[task].model ||
          route.temperature !== routes[task].temperature,
      ),
    );
    onSave(changed);
  }

  return (
    <div className="flex flex-col gap-3">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-border text-xs uppercase tracking-wide text-muted">
            <th className="px-3 py-2 text-start font-medium">{t("task")}</th>
            <th className="px-3 py-2 text-start font-medium">{t("provider")}</th>
            <th className="px-3 py-2 text-start font-medium">{t("model")}</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(draft).map(([task, route]) => (
            <tr key={task} className="border-b border-border/60">
              <td className="px-3 py-2">
                <span className="identifier text-xs">{task}</span>
              </td>
              <td className="px-3 py-2">
                <select
                  aria-label={`${task} ${t("provider")}`}
                  value={route.provider}
                  onChange={(event) => update(task, { provider: event.target.value })}
                  className="rounded border border-border bg-surface px-2 py-1 text-xs"
                >
                  {providers.map((provider) => (
                    <option key={provider} value={provider}>
                      {provider}
                    </option>
                  ))}
                </select>
              </td>
              <td className="px-3 py-2">
                <input
                  aria-label={`${task} ${t("model")}`}
                  value={route.model}
                  onChange={(event) => update(task, { model: event.target.value })}
                  className="w-full rounded border border-border bg-surface px-2 py-1 font-mono text-xs"
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="flex justify-end">
        <Button type="button" onClick={handleSave}>
          {t("save")}
        </Button>
      </div>
    </div>
  );
}
