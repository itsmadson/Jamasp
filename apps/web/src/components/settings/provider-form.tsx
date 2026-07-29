"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { TextField } from "@/components/ui/field";
import { REDACTED, type ProviderConfig } from "@/lib/api/settings";

const KNOWN_PROVIDERS = ["openrouter", "gapgpt", "local"];

export function ProviderForm({
  providers,
  onSave,
}: {
  providers: Record<string, ProviderConfig>;
  onSave: (providers: Record<string, ProviderConfig>) => void;
}) {
  const t = useTranslations("settings");
  const [draft, setDraft] = useState<Record<string, ProviderConfig>>(() =>
    Object.fromEntries(
      KNOWN_PROVIDERS.map((name) => [
        name,
        providers[name] ?? { base_url: "", api_key: "", extra_headers: null },
      ]),
    ),
  );

  function update(name: string, changes: Partial<ProviderConfig>) {
    setDraft((current) => ({ ...current, [name]: { ...current[name], ...changes } }));
  }

  function handleSave() {
    // Never send the redaction placeholder back: doing so would overwrite a real
    // stored key with a row of dots.
    const cleaned = Object.fromEntries(
      Object.entries(draft).map(([name, config]) => [
        name,
        { ...config, api_key: config.api_key === REDACTED ? "" : config.api_key },
      ]),
    );
    onSave(cleaned);
  }

  return (
    <div className="flex flex-col gap-6">
      {KNOWN_PROVIDERS.map((name) => (
        <div key={name} className="rounded-lg border border-border p-4">
          <h3 className="identifier mb-3 text-sm font-medium">{name}</h3>
          <div className="grid gap-3 sm:grid-cols-2">
            <TextField
              label={t("baseUrl")}
              value={draft[name].base_url}
              onChange={(event) => update(name, { base_url: event.target.value })}
            />
            <TextField
              label={t("apiKey")}
              type="password"
              autoComplete="off"
              value={draft[name].api_key}
              onChange={(event) => update(name, { api_key: event.target.value })}
              hint={t("apiKeyHint")}
            />
          </div>
        </div>
      ))}

      <div className="flex justify-end">
        <Button type="button" onClick={handleSave}>
          {t("save")}
        </Button>
      </div>
    </div>
  );
}
