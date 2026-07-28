# آگاه — S1: Connector & Semantic Layer (+ minimal platform shell)

**Date:** 2026-07-28
**Status:** Design, awaiting approval
**Scope:** Subsystem S1 of the آگاه platform, plus the thinnest slice of the platform shell (S5) needed to run it.

---

## 1. Product context

آگاه ("one who knows") is a report builder. A user asks a question in Persian or English —
*«افرادی که این ماه مرخصی گرفتند ولی تایم اداری بودند»*, *«گران‌ترین اجناس به تفکیک دسته‌بندی»* — and
the system queries connected data sources and renders an interactive report page with charts.

The full platform decomposes into five subsystems:

| # | Subsystem | Core job |
|---|-----------|----------|
| **S1** | **Connector & Semantic Layer** | Register a data source → introspect it → AI describes tables/columns/endpoints → human verifies → store as approved knowledge |
| S2 | Query Engine | Natural-language question → query plan → SQL/API/MCP call → validated, read-only execution → typed result set |
| S3 | Report Renderer | Result set + intent → generated React/Vite page (shadcn + charts) → built in Docker → served as a report artifact |
| S4 | Interactive Chat Edit | User chats at a rendered report → patch → rebuild → new version |
| S5 | Platform Shell | Next.js app, fa/en + RTL, auth, LLM provider abstraction, per-task model selection |

Dependencies: S1 → S2 → S3 → S4. S5 cuts across all of them.

**This document specifies S1 only**, plus the minimum of S5 required to make S1 usable
(auth, i18n, LLM provider abstraction, settings). S2/S3/S4 each get their own spec.

S1 was chosen first because every downstream subsystem consumes its output, and because the
"AI describes, human verifies" loop is the product's central premise — the place where being
wrong is most expensive and correction is cheapest.

### 1.1 What S1 delivers

An **approved semantic model**: a versioned, human-verified, machine-readable description of every
connected data source. S1 is complete when it can export that model as a stable JSON contract
(§9) that S2 can consume — which also makes S1 independently testable, with no part of S2 built.

---

## 2. Decisions taken

| Decision | Choice | Rationale |
|---|---|---|
| First subsystem | S1 + minimal shell | Everything downstream depends on trustworthy schema knowledge |
| Source types (v1) | PostgreSQL, MySQL/MariaDB, SQL Server, Oracle, REST, MCP | One adapter interface, six adapters behind it |
| Data exposure to LLM | Sampled values, PII-masked | Coded columns (`status=1,2,3`) and Persian enums are undecodable from schema alone |
| Review UX | Table-by-table cards, inline edit, explicit approve | Scales to 200-table databases; gives a clear "done" signal |
| Backend | Python 3.12 + FastAPI + SQLAlchemy | Reflection covers all four SQL dialects through one API; home of `sqlglot` and text-to-SQL tooling |
| Frontend | Next.js 15 (App Router) + shadcn/ui + Tailwind | Per user requirement; shadcn is also S3's component library, so the design system is shared |
| Tenancy | Single-org, multi-user, self-hosted | Customer DB credentials never leave the customer network |
| Schema drift | On-demand re-scan + delta review | Preserves human review effort; only new/changed objects need re-approval |
| Architecture | Deterministic introspection → LLM enrichment → structured store, with embeddings from day one | Determinism, testability, cheap delta re-scans; embeddings are mandatory because a 200-table schema does not fit in a prompt |

### 2.1 Architecture alternatives rejected

**Agentic explorer** — give the LLM tools (`list_tables`, `sample_table`, `run_readonly_query`) and
let it explore until it understands the database. Rejected: non-deterministic, expensive, two runs
cannot be diffed, and delta re-scan becomes near-impossible. Its genuine advantage is schemas with
no foreign keys, no comments, and cryptic names (`T_MST_01.FLD_003`, common in older Iranian
systems). Mitigated in the chosen design by the join-probe step (§5.3) and the human review UI.

**Free-text whole-DB document** — AI writes one markdown document describing the database, user
edits it as prose. Rejected: unstructured text is poor fuel for a SQL generator and impossible to
diff when the schema changes.

---

## 3. System architecture

```
┌─────────────────────────────────────────────────────────────┐
│  apps/web — Next.js 15                                      │
│  Sources list · Add source wizard · Scan progress (SSE)     │
│  Review UI (entity cards) · Settings (providers/models)     │
│  next-intl: fa (RTL, default) + en (LTR)                    │
└───────────────────────────┬─────────────────────────────────┘
                            │ REST + SSE (OpenAPI-typed)
┌───────────────────────────┴─────────────────────────────────┐
│  apps/api — FastAPI                                         │
│                                                             │
│  routers/   sources · scans · entities · settings · auth    │
│  adapters/  SourceAdapter protocol + 6 implementations      │
│  pipeline/  Introspector → Profiler → Describer → Embedder  │
│  llm/       Provider abstraction · task routing · cost log  │
│  safety/    PII classifier · read-only guard · masking      │
│  diff/      structural snapshot diff → entity status        │
└──────┬───────────────────────────┬──────────────────────────┘
       │                           │
┌──────┴────────┐          ┌───────┴────────┐
│ Postgres 16   │          │ Redis + arq    │
│ + pgvector    │          │ scan job queue │
│ metadata DB   │          └────────────────┘
└───────────────┘
                    ┌──────────────────────────────┐
                    │ Customer data sources        │
                    │ PG · MySQL · MSSQL · Oracle  │
                    │ REST (OpenAPI) · MCP servers │
                    └──────────────────────────────┘
```

**Repository layout** (monorepo, pnpm workspace + uv):

```
agah/
  apps/
    web/          Next.js 15
    api/          FastAPI
  packages/
    api-client/   generated from OpenAPI schema
  docker/
    compose.yml   api, web, postgres+pgvector, redis
    fixtures/     seeded test databases (PG, MySQL, MSSQL, Oracle)
  docs/superpowers/specs/
```

Frontend types are generated from the FastAPI OpenAPI schema — no hand-maintained duplicate types.

---

## 4. Data model (metadata database)

Postgres 16 with the `pgvector` extension. All timestamps UTC.

**`users`** — `id`, `email`, `password_hash` (argon2), `role` (`admin` | `analyst`), `locale`
(`fa` | `en`), `created_at`. Admin registers sources and approves descriptions; analyst consumes
approved knowledge (relevant from S2 onward).

**`data_sources`** — `id`, `name`, `kind` (`postgres` | `mysql` | `mssql` | `oracle` | `rest` |
`mcp`), `config_encrypted` (bytea), `sampling_policy` (`masked` | `schema_only`), `status`
(`draft` | `scanning` | `ready` | `error`), `created_by`, `created_at`, `last_scan_at`.

Credentials are encrypted at rest with AES-GCM, key from `AGAH_SECRET_KEY` (env). Credentials
are never returned by any API response — write-only fields, redacted on read.

**`scans`** — `id`, `data_source_id`, `status` (`queued` | `running` | `succeeded` | `partial` |
`failed`), `started_at`, `finished_at`, `structural_snapshot` (jsonb), `stats` (jsonb: entity
counts, token spend), `error` (jsonb: per-object failures). The snapshot is the complete
deterministic output of stage 1 — it is what the next scan diffs against.

**`entities`** — one row per table / view / REST endpoint / MCP tool.
`id`, `data_source_id`, `kind` (`table` | `view` | `endpoint` | `tool`), `schema_name`, `name`,
`structural` (jsonb), `structural_hash` (text), `description_ai` (jsonb), `description_human`
(jsonb), `status` (`pending` | `approved` | `stale` | `ignored` | `archived` | `describe_failed`) —
`ignored` means a human excluded it, `archived` means it no longer exists in the source,
`confidence` (real 0–1), `embedding` (vector(1024)), `version` (int), `approved_by`,
`approved_at`, `first_seen_scan_id`, `last_seen_scan_id`.

`description_ai` and `description_human` share a shape: `{ summary_fa, summary_en, grain,
business_domain, common_questions[] }`. AI output is never overwritten by human edits — both are
retained, and `description_human` wins wherever it is non-null. This keeps every human correction
auditable and reusable as few-shot material later.

**`fields`** — `id`, `entity_id`, `name`, `data_type`, `nullable`, `is_pk`, `ordinal`,
`stats` (jsonb: distinct count, null ratio, min/max, sampled distinct values post-masking),
`meaning_ai` (jsonb: `{fa, en}`), `meaning_human` (jsonb), `enum_map` (jsonb:
`{"1": {fa: "در انتظار", en: "pending"}, ...}`), `unit`, `pii_class` (`none` | `low` | `high`),
`confidence`, `status`.

**`relationships`** — `id`, `data_source_id`, `from_entity_id`, `from_field`, `to_entity_id`,
`to_field`, `kind` (`declared` | `inferred`), `cardinality`, `confidence`, `evidence` (jsonb:
join-probe hit rate), `status` (`pending` | `approved` | `rejected`).

Inferred relationships are first-class rows because in databases without declared foreign keys —
common in the target market — they are the single most valuable thing S1 produces for S2.

**`llm_calls`** — `id`, `scan_id`, `purpose`, `provider`, `model`, `tokens_in`, `tokens_out`,
`cost_usd`, `latency_ms`, `status`, `created_at`. Cost visibility per scan is required: describing
a 200-table database is a real expense the admin must be able to see before and after.

**`settings`** — `key`, `value` (jsonb), `updated_by`, `updated_at`. Holds provider config and
per-task model routing.

---

## 5. The scan pipeline

A scan is a background job (arq worker), resumable per stage, emitting progress over SSE.

```
[1 Introspect] → [2 Profile] → [3 Describe] → [4 Embed] → [5 Diff & stage] → review
   no AI          no AI          LLM            LLM         no AI
```

### 5.1 Stage 1 — Introspector (deterministic)

Per-adapter, no AI, fully snapshottable. SQL adapters use SQLAlchemy reflection for a uniform
result across all four dialects, plus dialect-specific queries for what reflection misses
(native table/column comments, approximate row counts, materialized views).

Emits a `StructuralSnapshot`: schemas, tables, views, columns with types/nullability/defaults,
primary keys, declared foreign keys, unique constraints, indexes, native comments, approximate
row counts.

REST adapter: fetch and parse the OpenAPI/Swagger document; each operation becomes an entity;
parameters and response schema properties become fields. MCP adapter: `tools/list` and
`resources/list`; each tool becomes an entity, its input-schema properties become fields.

Determinism is the point: this stage is testable against fixture databases with no LLM involved,
and its output is the diff basis for every future re-scan.

### 5.2 Stage 2 — Profiler (deterministic, privacy-critical)

For each column: distinct count, null ratio, min/max for ordered types. For low-cardinality
columns (distinct ≤ 50), the full distinct value list. Plus up to 20 sample rows per table.

Every value passes the PII classifier before leaving the process:

- **Rules** — column-name patterns (fa + en: `کدملی`, `national_id`, `شماره_موبایل`, `phone`,
  `iban`, `email`, `birth`, `address`, `salary`, `حقوق`), plus value-shape regexes (Iranian
  national ID checksum, IR IBAN, `09xxxxxxxxx` mobile, email, card numbers).
- **Classes** — `high`: never sampled, LLM sees name + type + statistics only. `low`: masked
  (`0912***4567`, `a***@example.com`, dates → year only). `none`: passed through.
- The `schema_only` sampling policy skips this stage entirely for a source.

Masking happens server-side before prompt assembly. No unmasked value can reach an external
provider — enforced by making the Describer's only input the Profiler's output type.

### 5.3 Stage 2b — Join probe (deterministic)

For databases with few or no declared foreign keys, generate candidate relationships from name and
type heuristics (`orders.customer_id` → `customers.id`; matching types; suffix/prefix conventions),
then test each candidate with a bounded read-only query measuring how many source values exist in
the target column. Above a hit-rate threshold, record an `inferred` relationship with its evidence.

This is evidence, not a guess, and it is the main compensation for rejecting the agentic-explorer
approach.

### 5.4 Stage 3 — Describer (LLM)

Input: one entity's structural record + profile + its immediate relationship neighborhood.
Batched by entity, with related entities included as context so the model can reason about joins.

Output is constrained to a JSON schema: table summary (fa **and** en, generated in one call),
grain, business domain, likely questions this table answers, per-column meaning (fa + en), enum
decodings for coded columns, units, and a self-reported confidence per field.

- Structured output enforced via the provider's JSON-schema mode where available; otherwise a
  parse-and-repair retry pass.
- Both languages in one call — cheaper than translating later, and it keeps the fa and en
  descriptions semantically identical.
- Entities exceeding the context budget (very wide tables) are split into column batches, with the
  table summary generated first and passed as context to each batch.
- Failure on one entity marks it `describe_failed` and continues; the scan finishes `partial` and
  failed entities are individually retryable from the UI.

### 5.5 Stage 4 — Embedder

Embed each approved-or-pending entity description (summary + column meanings + likely questions)
into `entities.embedding`. Bilingual text in one embedding, so a Persian question retrieves a table
described in either language.

Purpose: S2 selects the ~8 relevant tables for a question before generating SQL. Building this in
S1 avoids reprocessing every description later.

### 5.6 Stage 5 — Diff & stage

Compare `structural_hash` per entity against the previous scan's snapshot:

- **New** → `pending`, described.
- **Changed** → `stale`, re-described, human `description_human` retained and shown alongside a
  structural diff so the reviewer sees exactly what moved.
- **Unchanged** → untouched; `approved` stays `approved`, no LLM spend.
- **Removed** → `archived`, retained for history, excluded from export. Distinct from `ignored`,
  which is a human decision to exclude an object that still exists.

---

## 6. Review UI

Route: `/sources/[id]/review`.

**Layout** — left: entity list with status chips and filters (pending / stale / low-confidence /
approved / failed), search by name and by description. Right: the selected entity's card.

**Entity card** —
1. Header: name, kind, row count, status, confidence badge.
2. AI summary, editable inline; the AI original stays visible after editing.
3. Column table: name, type, AI meaning (editable), enum decoding editor for coded columns, PII
   class, per-field confidence. Low-confidence fields are visually flagged.
4. Relationships panel: declared FKs (read-only) and inferred ones (accept / reject, with the
   join-probe hit rate shown as evidence).
5. Actions: **Approve**, **Approve & next**, **Needs work** (leaves a note), **Ignore this table**.

**Bulk operations** — approve all entities above a confidence threshold; ignore a whole schema
(migration tables, audit logs, `_bak` tables). Necessary for 200-table databases.

**Progress** — "۴۷ of ۲۱۳ approved" with a persistent progress bar; approval is resumable across
sessions.

**Language** — the reviewer edits in their UI locale; the other language's text is kept and
flagged as possibly out of sync with a one-click "retranslate from my edit" action.

---

## 7. Platform shell (minimum S5 slice)

### 7.1 LLM provider abstraction

```python
class LLMProvider(Protocol):
    async def complete(self, messages, *, schema=None, model, **kw) -> Completion
    async def embed(self, texts, *, model) -> list[Vector]
```

Implementations: **GapGPT** (OpenAI-compatible base URL), **OpenRouter**, **OpenAI-compatible
local** (Ollama / vLLM / LM Studio — any base URL). All three are the same OpenAI-compatible
client differing in base URL, headers, and model naming, so the abstraction is thin by design.

**Per-task model routing** — configured in settings, not hardcoded:

| Task | Default | Why |
|---|---|---|
| `describe_entity` | `nvidia/nemotron-3-ultra-550b-a55b:free` (OpenRouter) | Strongest reasoning for inferring semantics from sparse structure |
| `describe_field_batch` | `inclusionai/ling-3.0-flash:free` (OpenRouter) | High-volume, low-difficulty pass; cost matters at 200 tables |
| `embed` | local embedding model, multilingual | Runs offline; keeps description text out of a third party |
| `translate` | `inclusionai/ling-3.0-flash:free` | Cheap |

Each task independently overridable (provider + model + temperature). Ordered fallback chain per
task, so a rate-limited free model degrades instead of failing the scan. Every call logged to
`llm_calls` with token counts and cost.

### 7.2 Secrets

**No API key is stored in the repository or in this document.** Configuration lives in `.env`
(gitignored, with a committed `.env.example` listing key names only) or is entered through the
settings UI and stored AES-GCM-encrypted in `settings`. Keys are redacted in every API response
and every log line.

The keys shared in chat during design are treated as compromised and must be rotated before use.

### 7.3 Auth

Email + password (argon2), JWT in an httpOnly cookie, two roles. Only `admin` may register
sources, run scans, approve descriptions, or change provider settings.

### 7.4 i18n

`next-intl`. Persian default, RTL, Vazirmatn; English LTR. Direction is a document-level attribute
driven by locale, not per-component. Persian digits and Jalali dates in fa locale (`dayjs` +
jalali plugin). All user-facing strings in message catalogs from the first commit — retrofitting
RTL and i18n later is far more expensive than doing it now.

---

## 8. Safety: read-only guarantee

S1 executes queries only during profiling and join probing, but the guard is built here because S2
depends on it and it is cheaper to establish once, correctly.

Four independent layers:

1. **Setup guidance** — documentation and the connection wizard steer the admin to a read-only
   database role. The strongest guarantee, and outside our control, so it is not the only one.
2. **AST validation** — every generated statement is parsed with `sqlglot` in the target dialect
   and rejected unless it is a single `SELECT` with no DML, DDL, CTE-with-write, or stacked
   statement. String matching is never used for this.
3. **Connection-level enforcement** — read-only transaction / session flags where the dialect
   supports them, autocommit off, statement timeout, and a row limit injected into every query.
4. **Resource bounds** — per-query timeout, max returned rows, max concurrent connections per
   source, so a probe cannot degrade a production database.

---

## 9. Output contract: the knowledge export

The deliverable S2 consumes. Versioned (`schema_version`), served at
`GET /api/sources/{id}/knowledge` and stable independent of internal storage.

```jsonc
{
  "schema_version": "1.0",
  "source": { "id": "...", "name": "HR System", "kind": "postgres", "dialect": "postgresql" },
  "generated_at": "2026-07-28T12:00:00Z",
  "entities": [
    {
      "id": "...", "kind": "table", "schema": "public", "name": "leave_requests",
      "summary": { "fa": "درخواست‌های مرخصی کارکنان", "en": "Employee leave requests" },
      "grain": "one row per leave request",
      "row_count_approx": 148230,
      "fields": [
        { "name": "status", "type": "smallint", "nullable": false,
          "meaning": { "fa": "وضعیت درخواست", "en": "Request status" },
          "enum_map": { "1": {"fa": "در انتظار", "en": "pending"},
                        "2": {"fa": "تایید شده", "en": "approved"},
                        "3": {"fa": "رد شده", "en": "rejected"} },
          "pii_class": "none" }
      ],
      "relationships": [
        { "from": "employee_id", "to": "employees.id",
          "kind": "declared", "cardinality": "many_to_one" }
      ],
      "sample_questions": ["افرادی که این ماه مرخصی گرفتند"]
    }
  ]
}
```

Only `approved` entities are exported. `pending`, `stale`, `describe_failed`, `ignored`, and
`archived` are excluded — S2 must never query data a human has not verified. This is what makes the human review
gate load-bearing rather than decorative.

---

## 10. Error handling

| Failure | Behavior |
|---|---|
| Connection fails at registration | Wizard shows the driver error verbatim plus a plain-language hint; source stays `draft` |
| Partial permissions (some schemas unreadable) | Introspect what is visible, record inaccessible objects in `scans.error`, finish `partial`, surface a banner naming what was skipped |
| LLM call fails / rate-limited | Retry with backoff, then the task's fallback model; on exhaustion mark that entity `describe_failed` and continue. Scan finishes `partial`; individual retry from the UI |
| Malformed LLM JSON | One repair pass with the validation error fed back; then `describe_failed` |
| Query timeout during profiling | Skip that column's statistics, keep structural data, note it on the entity |
| Very large schema (1000+ tables) | Paginated introspection, batched description, per-schema ignore before describing so the admin does not pay to describe tables they will never use |
| Scan interrupted (worker restart) | Stage boundaries are checkpointed; scan resumes at the last completed stage |
| Source unreachable during re-scan | Previous snapshot and approvals remain intact and exportable; re-scan fails without mutating state |
| Encryption key missing or rotated | API refuses to start with a clear message rather than serving requests that will fail per-source |

---

## 11. Testing strategy

**Adapters (integration)** — `docker-compose` fixtures for Postgres, MySQL, SQL Server, and Oracle,
each seeded with a schema that deliberately includes the hard cases: no declared FKs, cryptic
column names, Persian data, coded status columns, composite keys, views. Assert the
`StructuralSnapshot` matches a golden file per dialect. No LLM.

**Profiler & PII classifier (unit)** — golden tests over synthetic rows containing Iranian national
IDs, mobile numbers, IBANs, and Persian names. The critical assertion is negative: no `high`-class
value appears anywhere in the Describer's assembled prompt. This test is what makes the privacy
claim in §5.2 real rather than aspirational.

**Describer (unit, recorded)** — recorded provider responses (VCR-style cassettes); CI makes no
live LLM calls. Tests cover schema conformance, the repair path, batching of wide tables, and
per-entity failure isolation.

**Join probe (integration)** — fixture database with known-correct hidden relationships; assert
precision and recall against that ground truth.

**Diff engine (unit)** — snapshot pairs covering added / dropped / renamed / retyped columns;
assert the resulting entity statuses and that approved human text survives.

**Read-only guard (unit)** — an adversarial corpus per dialect: stacked statements, CTEs
containing writes, comment-obfuscated DDL, dialect-specific write syntax. Every one must be
rejected. Any bypass is a release blocker.

**End-to-end** — seed the Postgres fixture → register → scan → approve everything → export
knowledge → assert the export matches a golden contract file. This is the S1 acceptance test.

---

## 12. Acceptance criteria

1. An admin registers a PostgreSQL source through the wizard; connection errors are legible.
2. A scan runs to completion with live progress, and the admin can see its token cost.
3. Every table receives a bilingual description, per-column meanings, and enum decodings for coded
   columns.
4. Relationships absent from the schema are inferred with evidence and presented for approval.
5. No `high`-class PII value ever reaches an external LLM provider (proven by test, §11).
6. The admin reviews and approves table-by-table, resumable across sessions, with bulk approval
   above a confidence threshold.
7. Adding a column to the source and re-scanning marks only the affected table `stale`, preserves
   all other approvals, and shows a structural diff.
8. `GET /api/sources/{id}/knowledge` returns only approved entities, conforming to §9.
9. The whole flow works in Persian (RTL) and English, including Persian search over descriptions.
10. Switching the describe model from OpenRouter to a local Ollama model in settings requires no
    code change.
11. The same flow completes for MySQL, SQL Server, Oracle, a REST source, and an MCP source.

---

## 13. Out of scope

Question answering and SQL generation (S2); report page generation, Docker build orchestration,
and charts (S3); chat-driven report editing (S4); multi-tenancy; SSO/LDAP; write access to any
source; scheduled automatic scanning (on-demand only in v1).

---

## 14. Open questions for implementation planning

1. Oracle and SQL Server drivers (`oracledb`, `pyodbc`) need real fixture instances in CI; Oracle's
   container image is large and licensing-sensitive. Options: mark those adapter tests as an opt-in
   suite, or use Oracle XE. Decide before starting the Oracle adapter.
2. Embedding model choice — a local multilingual model (e.g. `bge-m3`) keeps description text off
   third-party infrastructure but adds a service to the deployment. Confirm the trade-off.
3. Confidence calibration — self-reported LLM confidence is unreliable. A cheap improvement is
   deriving confidence from structural evidence (does the column have a native comment? a declared
   FK? a recognizable name?) and blending it with the model's self-report. Worth prototyping during
   implementation.
