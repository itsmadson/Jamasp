"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { TextField } from "@/components/ui/field";
import { ApiError } from "@/lib/api/client";
import {
  createSource,
  testConnection,
  type ConnectionTestResult,
} from "@/lib/api/sources";
import type { SamplingPolicy, SourceKind, SourceOut } from "@/lib/api/types";

const KINDS: SourceKind[] = ["postgres", "mysql", "mssql", "oracle", "rest", "mcp"];

interface AddSourceDialogProps {
  open: boolean;
  onClose: () => void;
  onCreated: (source: SourceOut) => void;
}

export function AddSourceDialog({ open, onClose, onCreated }: AddSourceDialogProps) {
  const t = useTranslations("sources");
  const common = useTranslations("common");

  const [name, setName] = useState("");
  const [kind, setKind] = useState<SourceKind>("postgres");
  const [dsn, setDsn] = useState("");
  const [samplingPolicy, setSamplingPolicy] = useState<SamplingPolicy>("masked");
  const [proven, setProven] = useState<ConnectionTestResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  function updateDsn(value: string) {
    setDsn(value);
    // A proof applies to the string it was run against. Editing invalidates it,
    // otherwise an admin could prove one DSN and save a different one.
    setProven(null);
  }

  async function handleTest() {
    setError(null);
    setPending(true);
    try {
      const result = await testConnection(kind, dsn);
      setProven(result.healthy ? result : null);
      if (!result.healthy) setError(result.error ?? t("connectionFailed"));
    } catch (caught) {
      setProven(null);
      setError(caught instanceof ApiError ? caught.detail : t("connectionFailed"));
    } finally {
      setPending(false);
    }
  }

  async function handleSave() {
    setError(null);
    setPending(true);
    try {
      const source = await createSource({
        name,
        kind,
        dsn,
        sampling_policy: samplingPolicy,
      });
      onCreated(source);
      // Drop the credential from component state the moment it is no longer needed.
      setDsn("");
      setProven(null);
      onClose();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.detail : t("saveFailed"));
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={t("addTitle")}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} type="button">
            {common("cancel")}
          </Button>
          <Button onClick={handleSave} disabled={!proven || !name || pending} type="button">
            {common("save")}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <TextField
          label={t("name")}
          value={name}
          onChange={(event) => setName(event.target.value)}
        />

        <div className="flex flex-col gap-1.5">
          <label htmlFor="source-kind" className="text-sm font-medium">
            {t("kind")}
          </label>
          <select
            id="source-kind"
            value={kind}
            onChange={(event) => {
              setKind(event.target.value as SourceKind);
              setProven(null);
            }}
            className="rounded-md border border-border bg-surface px-3 py-2 text-sm"
          >
            {KINDS.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </div>

        <TextField
          label={t("connectionString")}
          type="password"
          autoComplete="off"
          value={dsn}
          onChange={(event) => updateDsn(event.target.value)}
          hint={t("connectionHint")}
        />

        <div className="flex flex-col gap-1.5">
          <label htmlFor="sampling-policy" className="text-sm font-medium">
            {t("samplingPolicy")}
          </label>
          <select
            id="sampling-policy"
            value={samplingPolicy}
            onChange={(event) => setSamplingPolicy(event.target.value as SamplingPolicy)}
            className="rounded-md border border-border bg-surface px-3 py-2 text-sm"
          >
            <option value="masked">{t("samplingMasked")}</option>
            <option value="schema_only">{t("samplingSchemaOnly")}</option>
          </select>
          <p className="text-xs text-muted">{t("samplingHint")}</p>
        </div>

        <div className="flex items-center gap-3">
          <Button variant="secondary" onClick={handleTest} disabled={!dsn || pending} type="button">
            {t("testConnection")}
          </Button>
          {proven ? (
            <p className="text-sm text-accent">✓ {proven.server_version}</p>
          ) : null}
        </div>

        {error ? (
          <p role="alert" className="rounded-md bg-danger/10 px-3 py-2 text-sm text-danger">
            {error}
          </p>
        ) : null}
      </div>
    </Dialog>
  );
}
