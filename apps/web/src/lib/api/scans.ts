import { apiFetch } from "./client";
import type { ScanOut } from "./types";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type ScanStage =
  | "introspect"
  | "profile"
  | "probe"
  | "describe"
  | "embed"
  | "diff"
  | "status"
  | "done";

export interface ScanProgressEvent {
  stage: ScanStage;
  current?: number;
  total?: number;
  message?: string;
  status?: string;
}

export function getScan(id: string): Promise<ScanOut> {
  return apiFetch<ScanOut>(`/api/scans/${id}`);
}

export function scanEventsUrl(id: string): string {
  return `${BASE_URL}/api/scans/${id}/events`;
}
