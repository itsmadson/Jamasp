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

export type ReportStatus = "queued" | "running" | "succeeded" | "partial" | "failed";

export type Column = { name: string; type: "number" | "text" | "temporal" | "boolean" };

/** One panel: its own question, its own SQL, its own rows. */
export interface ReportDataset {
  key: string;
  question: string | null;
  sql: string | null;
  explanation: Bilingual | null;
  columns: Column[];
  rows: Record<string, unknown>[];
  row_count: number;
  error: string | null;
  /** Arithmetic over this panel's rows, recomputed on every read. */
  facts: Record<string, unknown>;
  /** Plain prose about this panel, from those facts. */
  narrative: Bilingual | null;
}

export interface Report extends ReportSummary {
  status: ReportStatus;
  error: string | null;
  question: string | null;
  spec: ReportSpec;
  datasets: ReportDataset[];
  // The first panel, flat. Older callers still read these.
  sql: string | null;
  explanation: Bilingual | null;
  columns: Column[];
  rows: Record<string, unknown>[];
  row_count: number;
}

export type ReportStage = "plan" | "query" | "design" | "status" | "done";

export interface ReportProgressEvent {
  stage: ReportStage;
  current?: number;
  total?: number;
  message?: string;
  status?: string;
}

// Empty means same-origin: requests go to /api/... and Next proxies them.
const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

export function reportEventsUrl(id: string): string {
  return `${BASE_URL}/api/reports/${id}/events`;
}

/**
 * Queues the build and returns immediately.
 *
 * The report comes back empty with status "queued". Follow reportEventsUrl for
 * the steps, then getReport once it is done — building takes several model calls,
 * and holding a request open that long only produced a timeout the user read as a
 * crash while the work quietly succeeded.
 */
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
