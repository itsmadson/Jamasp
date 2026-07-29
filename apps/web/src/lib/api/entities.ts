import { apiFetch } from "./client";
import type {
  Bilingual,
  EntityDescription,
  EntityListOut,
  EntityOut,
  EntityStatus,
} from "./types";

export interface EntityFilters {
  status?: EntityStatus;
  min_confidence?: number;
  q?: string;
  sort?: "name" | "confidence_asc" | "status";
  limit?: number;
  offset?: number;
}

export interface FieldPatch {
  id: string;
  meaning_human?: Bilingual;
  enum_map?: Record<string, Bilingual>;
  unit?: string;
}

export interface EntityPatch {
  description_human?: EntityDescription;
  fields?: FieldPatch[];
}

export function listEntities(
  sourceId: string,
  filters: EntityFilters = {},
): Promise<EntityListOut> {
  const query = new URLSearchParams(
    Object.entries(filters)
      .filter(([, value]) => value !== undefined && value !== "")
      .map(([key, value]) => [key, String(value)]),
  );
  return apiFetch<EntityListOut>(`/api/sources/${sourceId}/entities?${query}`);
}

export function getEntity(id: string): Promise<EntityOut> {
  return apiFetch<EntityOut>(`/api/entities/${id}`);
}

export function patchEntity(id: string, patch: EntityPatch): Promise<EntityOut> {
  return apiFetch<EntityOut>(`/api/entities/${id}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export function approveEntity(id: string): Promise<EntityOut> {
  return apiFetch<EntityOut>(`/api/entities/${id}/approve`, { method: "POST" });
}

export function ignoreEntity(id: string): Promise<EntityOut> {
  return apiFetch<EntityOut>(`/api/entities/${id}/ignore`, { method: "POST" });
}

export function bulkApprove(
  sourceId: string,
  minConfidence: number,
): Promise<{ approved_count: number }> {
  return apiFetch<{ approved_count: number }>(
    `/api/sources/${sourceId}/entities/bulk-approve`,
    { method: "POST", body: JSON.stringify({ min_confidence: minConfidence }) },
  );
}
