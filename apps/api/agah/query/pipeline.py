"""Question in, answered result set out."""

import json
import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from agah.adapters.base import SourceAdapter
from agah.llm.router import call_task
from agah.query.prompts.generate_sql import GENERATE_SQL_SCHEMA, build_sql_messages
from agah.query.retrieve import select_tables
from agah.query.validate import UnsafeQueryError, validate_sql

DEFAULT_ROW_LIMIT = 1000
DEFAULT_TIMEOUT_S = 30


class QueryFailed(Exception):
    def __init__(self, status: str, message: str, sql: str | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.sql = sql


@dataclass
class QueryResult:
    question: str
    sql: str
    explanation: dict[str, str]
    tables_used: list[str]
    columns: list[dict[str, str]]
    rows: list[dict[str, Any]]
    row_count: int
    duration_ms: int
    assumptions: list[str] = field(default_factory=list)


def infer_columns(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Types come from the data itself so S3 can pick chart forms without guessing."""
    if not rows:
        return []

    columns: list[dict[str, str]] = []
    for name in rows[0]:
        sample = next((row[name] for row in rows if row[name] is not None), None)
        if isinstance(sample, bool):
            kind = "boolean"
        elif isinstance(sample, int | float):
            kind = "number"
        elif hasattr(sample, "isoformat"):
            kind = "temporal"
        else:
            kind = "text"
        columns.append({"name": name, "type": kind})
    return columns


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    return str(value)


async def answer_question(
    session: AsyncSession,
    adapter: SourceAdapter,
    knowledge: dict[str, Any],
    question: str,
    locale: str = "fa",
    row_limit: int = DEFAULT_ROW_LIMIT,
) -> QueryResult:
    dialect = knowledge.get("source", {}).get("dialect", "postgres")
    approved = {entity["name"] for entity in knowledge.get("entities", [])}

    selected = select_tables(question, knowledge)
    if not selected:
        raise QueryFailed(
            "no_match",
            "No approved table matches this question. "
            "Either the data is not connected, or its description needs review.",
        )

    messages = build_sql_messages(question, selected, dialect, locale)
    completion = await call_task(
        session, "generate_sql", messages, schema=GENERATE_SQL_SCHEMA
    )

    try:
        payload = json.loads(completion.text)
    except json.JSONDecodeError:
        repair = [
            *messages,
            {"role": "assistant", "content": completion.text},
            {"role": "user", "content": "That was not valid JSON. Reply with JSON only."},
        ]
        retry = await call_task(
            session, "generate_sql", repair, schema=GENERATE_SQL_SCHEMA
        )
        try:
            payload = json.loads(retry.text)
        except json.JSONDecodeError as exc:
            raise QueryFailed("generation_failed", f"model returned no usable JSON: {exc}") from exc

    sql = (payload.get("sql") or "").strip()
    explanation = payload.get("explanation") or {"fa": "", "en": ""}
    if not sql:
        # The model was told to say so rather than invent a query it cannot support.
        raise QueryFailed(
            "no_match", explanation.get(locale) or explanation.get("en") or "unanswerable"
        )

    try:
        bounded = validate_sql(sql, approved, dialect, row_limit)
    except UnsafeQueryError as exc:
        raise QueryFailed("unsafe", str(exc), sql=sql) from exc

    started = time.perf_counter()
    try:
        raw_rows = await adapter.execute_readonly(
            bounded, limit=row_limit, timeout_s=DEFAULT_TIMEOUT_S
        )
    except Exception as exc:
        raise QueryFailed("execution_failed", str(exc), sql=bounded) from exc
    duration_ms = int((time.perf_counter() - started) * 1000)

    rows = [{key: _jsonable(value) for key, value in row.items()} for row in raw_rows]

    return QueryResult(
        question=question,
        sql=bounded,
        explanation=explanation,
        tables_used=payload.get("tables_used") or [entity["name"] for entity in selected],
        columns=infer_columns(rows),
        rows=rows,
        row_count=len(rows),
        duration_ms=duration_ms,
        assumptions=payload.get("assumptions") or [],
    )
