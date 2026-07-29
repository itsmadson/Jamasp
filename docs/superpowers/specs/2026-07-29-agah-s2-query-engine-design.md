# آگاه — S2: Natural-language Query Engine

**Date:** 2026-07-29
**Status:** Design
**Depends on:** S1 (`docs/superpowers/specs/2026-07-28-agah-s1-semantic-layer-design.md`)

## 1. What this builds

A Persian or English question becomes a validated, read-only SQL query, executed
against the customer's database, returning a typed result set.

*«افرادی که این ماه مرخصی گرفتند»* → `SELECT ... FROM leave_requests JOIN employees ...`
→ rows.

S2 consumes exactly one thing: S1's knowledge export (`GET /api/sources/{id}/knowledge`),
which contains only human-approved descriptions. It never reads unapproved metadata —
that is what makes the S1 review gate meaningful rather than decorative.

## 2. Pipeline

```
question ──▶ [1 Retrieve] ──▶ [2 Generate] ──▶ [3 Validate] ──▶ [4 Execute] ──▶ ResultSet
              no AI            LLM              no AI            no AI
```

**Stage 1 — Retrieve.** A 200-table schema does not fit in a prompt, so the engine
selects the handful of tables a question touches. Two strategies, tried in order:

- **Vector search** over `entities.embedding` when embeddings exist.
- **Lexical fallback** — scoring over table names, column names, bilingual summaries
  and `common_questions`.

The fallback is not a degraded nicety: S1 already proved that a self-hosted install
with no embedding service is a normal state. A query engine that only works when
Ollama is running would be broken for a large share of deployments.

Retrieved tables are expanded along approved relationships one hop, because a question
about leave requests almost always needs the employee table to be answerable.

**Stage 2 — Generate.** The selected subset of the knowledge export is rendered as a
compact schema description — table purpose, column meanings, **enum decodings**, and
join paths — and sent with the question. Enum decodings are the highest-value part:
without them the model writes `WHERE status = 'approved'` against a smallint column.

Output is structured: `{sql, explanation: {fa, en}, tables_used, assumptions}`. The
explanation is required, not decorative — a user who cannot read SQL still has to
judge whether the query answered their question.

**Stage 3 — Validate.** Reuses `safety.readonly.assert_readonly` from S1 unchanged,
plus:
- every table referenced must be in the approved export (a hallucinated table name is
  rejected before it reaches the database),
- a row limit is injected,
- the statement is re-parsed in the source's dialect.

**Stage 4 — Execute.** Through the existing `SourceAdapter.execute_readonly`, with a
statement timeout. Column types are inferred from the returned rows so S3 can pick
chart forms without guessing.

## 3. Failure handling

| Failure | Behavior |
|---|---|
| No relevant table found | Return `no_match` with the tables that were considered, rather than inventing a query |
| Model returns invalid SQL | One repair pass with the parser error; then `generation_failed` |
| SQL references an unapproved table | Rejected as `unsafe`, never executed |
| Query times out | `timeout` with the elapsed time; the SQL is returned so a human can inspect it |
| Query returns nothing | Success with zero rows — an empty answer is an answer, not an error |

## 4. Data model additions

**`queries`** — `id`, `data_source_id`, `question`, `locale`, `sql`, `explanation`
(jsonb), `tables_used` (jsonb), `status`, `row_count`, `duration_ms`, `error`,
`created_by`, `created_at`. Query history is what S4 later edits and what makes a
report reproducible.

## 5. Model routing

A new task, `generate_sql`, routed like every other task through
`llm.router.call_task`. Default is the strongest available model, because SQL
generation with multi-table joins is the hardest reasoning in the product — a wrong
join silently produces a plausible, incorrect report.

## 6. Out of scope

Chart selection and page rendering (S3), conversational refinement (S4), caching,
and query cost estimation.

## 7. Acceptance criteria

1. A Persian question against the fixture HR database returns correct rows.
2. The generated SQL decodes coded columns using the approved enum map.
3. A question needing a join uses the inferred `leave_requests.emp_id → employees.id`
   relationship that no foreign key declares.
4. Retrieval works with no embeddings present.
5. A question about data the source does not contain returns `no_match`, not a guess.
6. Generated SQL containing a write, or naming an unapproved table, is never executed.
7. Every result carries a bilingual explanation of what the query did.
