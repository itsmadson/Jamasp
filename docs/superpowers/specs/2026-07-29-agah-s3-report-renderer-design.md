# آگاه — S3: Report Renderer

**Date:** 2026-07-29
**Status:** Design
**Depends on:** S2 (`docs/superpowers/specs/2026-07-29-agah-s2-query-engine-design.md`)

## 1. What this builds

A question becomes a report page: title, summary, KPI tiles, charts, and a table —
laid out by the AI, rendered in Persian or English, saved and shareable.

S2 already answers questions. S3 decides *how the answer should look* and renders it.

## 2. The architecture decision

The original idea was a Docker container per report running a Vite build over
AI-generated React source. This design keeps the outcome — a custom, AI-designed
page — but changes what the AI produces.

**The AI authors a declarative `ReportSpec` (JSON), not component source.**

| | AI writes TSX | AI writes a spec |
|---|---|---|
| Failure mode | Does not compile → no report at all | Fails schema validation → repair pass, or fall back to a table |
| Time to first render | A Vite build per report (tens of seconds) | Immediate |
| S4 chat editing | Regenerate and rebuild the whole file | Patch one field of the spec |
| Reviewability | A diff of generated code | A diff of intent |
| Attack surface | Executing model-authored code | Data rendered by trusted components |

The last row is the decisive one: rendering model-authored JavaScript in a page that
also holds a session cookie is a code-execution path driven by the contents of a
customer's database. The spec approach never executes anything the model wrote.

A Vite build still exists, but once — for the renderer itself, which ships with the
app. Per-report *export* to a standalone bundle is a later addition and is noted in
§8 rather than pretended to be built.

## 3. ReportSpec

```jsonc
{
  "schema_version": "1.0",
  "title": {"fa": "مرخصی‌های تاییدشده", "en": "Approved leave"},
  "summary": {"fa": "…", "en": "…"},
  "blocks": [
    {"type": "kpi",   "label": {...}, "column": "total", "aggregate": "sum", "unit": null},
    {"type": "bar",   "title": {...}, "x": "status_label", "y": "request_count", "series": null},
    {"type": "line",  "title": {...}, "x": "month", "y": "count", "series": "department"},
    {"type": "table", "title": {...}, "columns": ["full_name", "start_date"]}
  ]
}
```

Every block names columns that must exist in the result set. A block referencing an
absent column is dropped during validation rather than rendered broken — the model
occasionally invents a column name, and one bad block should not cost the whole page.

**Block types in v1:** `kpi`, `bar`, `line`, `table`. Deliberately small. A chart type
the renderer does not implement is worse than no chart, and these four cover the
report shapes the product's example questions produce.

## 4. Choosing the form

The model picks blocks, but the *rules* are enforced in code because they are not
judgement calls:

- One temporal column plus one numeric → line.
- One low-cardinality text column plus one numeric → bar.
- A single row with a single numeric → kpi.
- Anything else, or more than 200 rows → table.

The model's choice is accepted when it is consistent with the data's shape and
overridden when it is not. This is what keeps a pie chart off a time series.

## 5. Pipeline

```
question ─▶ S2 answer ─▶ [generate spec] ─▶ [validate + coerce] ─▶ [persist] ─▶ render
              rows        LLM                 no AI                 no AI
```

Reports are stored with their spec **and** their query, so a report can be re-run
against fresh data without asking the model again.

## 6. Data model

**`reports`** — `id`, `data_source_id`, `query_id`, `title` (jsonb), `spec` (jsonb),
`locale`, `created_by`, `created_at`, `updated_at`.

## 7. Failure handling

| Failure | Behavior |
|---|---|
| Model returns invalid JSON | One repair pass, then fall back to a table-only spec |
| Block names a column that is not in the result | Drop that block, keep the rest |
| Every block invalid | Table-only spec — the data still reaches the user |
| Result set empty | Render the title and an explicit empty state, not a blank page |

A report that renders the data plainly always beats an error page.

## 8. Out of scope

Chat-driven editing (S4), export to a standalone bundle, scheduled refresh, PDF
export, and sharing links with their own access control.

## 9. Acceptance criteria

1. A Persian question produces a report with a Persian title, summary and chart labels.
2. Counts grouped by a category render as a bar chart, not a table.
3. A single aggregate value renders as a KPI tile.
4. A block naming a column absent from the result is dropped, and the report still renders.
5. An empty result set renders an explicit empty state.
6. Charts are legible in both light and dark themes and in RTL.
7. Nothing the model wrote is executed as code.
