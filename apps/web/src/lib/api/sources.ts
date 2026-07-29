import { apiFetch } from "./client";
import type { SamplingPolicy, ScanOut, SourceKind, SourceOut } from "./types";

export interface ConnectionTestResult {
  healthy: boolean;
  server_version: string;
  error: string | null;
}

export interface SourceCreateInput {
  name: string;
  kind: SourceKind;
  dsn: string;
  sampling_policy?: SamplingPolicy;
}

export function listSources(): Promise<SourceOut[]> {
  return apiFetch<SourceOut[]>("/api/sources");
}

export function getSource(id: string): Promise<SourceOut> {
  return apiFetch<SourceOut>(`/api/sources/${id}`);
}

export function createSource(input: SourceCreateInput): Promise<SourceOut> {
  return apiFetch<SourceOut>("/api/sources", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function testConnection(kind: SourceKind, dsn: string): Promise<ConnectionTestResult> {
  return apiFetch<ConnectionTestResult>("/api/sources/test-connection", {
    method: "POST",
    body: JSON.stringify({ kind, dsn }),
  });
}

export function deleteSource(id: string): Promise<void> {
  return apiFetch<void>(`/api/sources/${id}`, { method: "DELETE" });
}

export function startScan(sourceId: string): Promise<ScanOut> {
  return apiFetch<ScanOut>(`/api/sources/${sourceId}/scans`, { method: "POST" });
}
