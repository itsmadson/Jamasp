import { apiFetch } from "./client";

export const REDACTED = "••••••••";

export interface ProviderConfig {
  base_url: string;
  api_key: string;
  extra_headers: Record<string, string> | null;
}

export interface RouteConfig {
  provider: string;
  model: string;
  temperature: number;
  fallbacks: [string, string][];
}

export interface LLMSettings {
  providers: Record<string, ProviderConfig>;
  routes: Record<string, RouteConfig>;
}

export function getLLMSettings(): Promise<LLMSettings> {
  return apiFetch<LLMSettings>("/api/settings/llm");
}

export function updateProviders(
  providers: Record<string, ProviderConfig>,
): Promise<LLMSettings> {
  return apiFetch<LLMSettings>("/api/settings/llm/providers", {
    method: "PUT",
    body: JSON.stringify({ providers }),
  });
}

export function updateRoutes(routes: Record<string, RouteConfig>): Promise<LLMSettings> {
  return apiFetch<LLMSettings>("/api/settings/llm/routes", {
    method: "PUT",
    body: JSON.stringify({ routes }),
  });
}
