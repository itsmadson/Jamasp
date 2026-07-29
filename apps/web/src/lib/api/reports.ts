import { ApiError, apiFetch } from "./client";
import { QueryRefused, type QueryFailureStatus } from "./query";
import type { Bilingual } from "./types";
import type { ReportSpec } from "@/components/report/report-view";

export interface ReportSummary {
  id: string;
  data_source_id: string;
  title: Bilingual;
  locale: string;
  created_at: string;
}

export interface Report extends ReportSummary {
  spec: ReportSpec;
  sql: string | null;
  explanation: Bilingual | null;
  columns: { name: string; type: "number" | "text" | "temporal" | "boolean" }[];
  rows: Record<string, unknown>[];
  row_count: number;
}

export async function createReport(
  sourceId: string,
  question: string,
  locale: string,
): Promise<Report> {
  try {
    return await apiFetch<Report>(`/api/sources/${sourceId}/reports`, {
      method: "POST",
      body: JSON.stringify({ question, locale }),
    });
  } catch (error) {
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

export function listReports(sourceId: string): Promise<ReportSummary[]> {
  return apiFetch<ReportSummary[]>(`/api/sources/${sourceId}/reports`);
}

export function getReport(reportId: string): Promise<Report> {
  return apiFetch<Report>(`/api/reports/${reportId}`);
}

export async function editReport(
  reportId: string,
  instruction: string,
  locale: string,
): Promise<Report> {
  try {
    return await apiFetch<Report>(`/api/reports/${reportId}/chat`, {
      method: "POST",
      body: JSON.stringify({ instruction, locale }),
    });
  } catch (error) {
    if (error instanceof ApiError && error.status === 422) {
      const detail = error.payload as { status?: string; message?: string } | null;
      if (detail?.status) {
        // A rejected edit is a considered answer: the report is unchanged.
        throw new QueryRefused(
          detail.status as QueryFailureStatus,
          detail.message ?? "",
          null,
        );
      }
    }
    throw error;
  }
}
