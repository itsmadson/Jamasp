import { ApiError, apiFetch } from "./client";
import type { Bilingual } from "./types";

export type QueryFailureStatus =
  | "no_match"
  | "generation_failed"
  | "unsafe"
  | "execution_failed";

export interface AskResponse {
  id: string;
  question: string;
  sql: string;
  explanation: Bilingual;
  tables_used: string[];
  assumptions: string[];
  columns: { name: string; type: "number" | "text" | "temporal" | "boolean" }[];
  rows: Record<string, unknown>[];
  row_count: number;
  duration_ms: number;
}

export class QueryRefused extends Error {
  constructor(
    readonly status: QueryFailureStatus,
    message: string,
    readonly sql: string | null,
  ) {
    super(message);
    this.name = "QueryRefused";
  }
}

export async function ask(
  sourceId: string,
  question: string,
  locale: string,
): Promise<AskResponse> {
  try {
    return await apiFetch<AskResponse>(`/api/sources/${sourceId}/query`, {
      method: "POST",
      body: JSON.stringify({ question, locale }),
    });
  } catch (error) {
    // A refusal is a normal outcome carrying structure, not a transport failure:
    // the engine declined to answer and said why.
    if (error instanceof ApiError && error.status === 422) {
      const detail = error.payload as
        | { status?: string; message?: string; sql?: string | null }
        | null;
      if (detail?.status) {
        throw new QueryRefused(
          detail.status as QueryFailureStatus,
          detail.message ?? "",
          detail.sql ?? null,
        );
      }
    }
    throw error;
  }
}

export interface QueryHistoryEntry {
  id: string;
  question: string;
  locale: string;
  sql: string | null;
  explanation: Bilingual | null;
  status: string;
  row_count: number | null;
  duration_ms: number | null;
  error: string | null;
  created_at: string;
}

export function queryHistory(sourceId: string): Promise<QueryHistoryEntry[]> {
  return apiFetch<QueryHistoryEntry[]>(`/api/sources/${sourceId}/queries`);
}
