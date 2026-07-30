import { apiFetch } from "./client";

/** Where one source sits in the scan → review → ask journey. */
export interface SourceProgress {
  id: string;
  name: string;
  kind: string;
  status: string;
  last_scan_at: string | null;
  last_scan_status: string | null;
  entities_total: number;
  entities_approved: number;
  entities_pending: number;
  reports: number;
  questions: number;
  next_step: "scan" | "scanning" | "review" | "ask" | "ready";
}

export interface ActivityItem {
  kind: "question" | "report";
  id: string;
  data_source_id: string;
  title: string;
  status: string;
  created_at: string;
}

export interface Overview {
  sources: SourceProgress[];
  recent: ActivityItem[];
  totals: Record<string, number>;
}

export function getOverview(): Promise<Overview> {
  return apiFetch<Overview>("/api/overview");
}
