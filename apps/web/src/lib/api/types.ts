/**
 * Hand-written mirrors of the FastAPI schemas in apps/api/jamasp/schemas/.
 * Small and stable enough that a codegen step would cost more than it saves.
 */

export type Bilingual = { fa: string; en: string };

export type SourceKind = "postgres" | "mysql" | "mssql" | "rest";
export type SourceStatus = "draft" | "scanning" | "ready" | "error";
export type SamplingPolicy = "masked" | "schema_only";
export type ScanStatus = "queued" | "running" | "succeeded" | "partial" | "failed";
export type PIIClass = "none" | "low" | "high";
export type EntityStatus =
  | "pending"
  | "approved"
  | "stale"
  | "ignored"
  | "archived"
  | "describe_failed";

export interface SourceOut {
  id: string;
  name: string;
  kind: SourceKind;
  sampling_policy: SamplingPolicy;
  status: SourceStatus;
  created_at: string;
  last_scan_at: string | null;
}

export interface ScanOut {
  id: string;
  data_source_id: string;
  status: ScanStatus;
  started_at: string | null;
  finished_at: string | null;
  stats: { llm_calls?: number; tokens_in?: number; tokens_out?: number } | null;
  error: { failures?: { entity: string; error: string }[]; fatal?: string } | null;
}

export interface FieldOut {
  id: string;
  name: string;
  data_type: string;
  nullable: boolean;
  is_pk: boolean;
  ordinal: number;
  meaning_ai: Bilingual | null;
  meaning_human: Bilingual | null;
  enum_map: Record<string, Bilingual> | null;
  unit: string | null;
  pii_class: PIIClass;
  confidence: number | null;
}

export interface EntitySummaryOut {
  id: string;
  kind: string;
  schema_name: string;
  name: string;
  status: EntityStatus;
  confidence: number | null;
  row_count_approx: number | null;
  version: number;
}

export interface EntityDescription {
  summary?: Bilingual;
  grain?: string;
  business_domain?: string;
  common_questions?: string[];
  confidence?: number;
}

export interface EntityOut extends EntitySummaryOut {
  structural: Record<string, unknown>;
  description_ai: EntityDescription | null;
  description_human: EntityDescription | null;
  approved_by: string | null;
  approved_at: string | null;
  fields: FieldOut[];
}

export interface EntityListOut {
  items: EntitySummaryOut[];
  total: number;
}
