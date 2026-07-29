"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { ApiError } from "@/lib/api/client";
import {
  getLLMSettings,
  updateProviders,
  updateRoutes,
  type LLMSettings,
} from "@/lib/api/settings";

import { ProviderForm } from "./provider-form";
import { RouteTable } from "./route-table";

export function SettingsScreen() {
  const t = useTranslations("settings");
  const [settings, setSettings] = useState<LLMSettings | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getLLMSettings()
      .then(setSettings)
      .catch((caught) =>
        setError(caught instanceof ApiError ? caught.detail : t("failed")),
      );
  }, [t]);

  async function run(action: () => Promise<LLMSettings>) {
    setError(null);
    setMessage(null);
    try {
      setSettings(await action());
      setMessage(t("saved"));
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.detail : t("failed"));
    }
  }

  if (!settings) {
    return <p className="text-sm text-muted">{error ?? "…"}</p>;
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-10">
      <h1 className="text-2xl font-bold tracking-tight">{t("title")}</h1>

      {message ? <p className="text-sm text-accent">{message}</p> : null}
      {error ? (
        <p role="alert" className="rounded-md bg-danger/10 px-3 py-2 text-sm text-danger">
          {error}
        </p>
      ) : null}

      <section>
        <h2 className="text-lg font-medium">{t("llmTitle")}</h2>
        <p className="mb-4 text-sm text-muted">{t("llmSubtitle")}</p>
        <RouteTable
          routes={settings.routes}
          providers={Object.keys(settings.providers).length > 0
            ? Object.keys(settings.providers)
            : ["openrouter", "gapgpt", "local"]}
          onSave={(changed) => run(() => updateRoutes(changed))}
        />
      </section>

      <section>
        <h2 className="text-lg font-medium">{t("providersTitle")}</h2>
        <p className="mb-4 text-sm text-muted">{t("providersSubtitle")}</p>
        <ProviderForm
          providers={settings.providers}
          onSave={(providers) => run(() => updateProviders(providers))}
        />
      </section>
    </div>
  );
}
