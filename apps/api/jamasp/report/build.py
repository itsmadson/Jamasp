"""Build a report off the request path, reporting each step as it happens.

A report is several model calls — plan the panels, write SQL for each, design the
layout — and on a slow provider that is minutes. Held open as one HTTP request it
times out, the browser shows a 500, and the work completes anyway and looks lost.
So it runs as a job and publishes progress, the same way a scan does.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from jamasp.adapters.registry import adapter_for
from jamasp.llm.router import call_task
from jamasp.models.query import Query, QueryStatus
from jamasp.models.report import Report, ReportStatus
from jamasp.models.source import DataSource
from jamasp.pipeline.orchestrator import decrypt_config
from jamasp.query.pipeline import QueryFailed, answer_question
from jamasp.report.insights import describe_panel
from jamasp.report.prompts.design_report import REPORT_SCHEMA, build_report_messages
from jamasp.report.prompts.plan_report import PLAN_SCHEMA, build_plan_messages
from jamasp.report.spec import coerce_spec, fallback_spec

# More panels than this is a dashboard nobody reads, and one query per panel means
# the cost is real.
MAX_PANELS = 6


@dataclass
class ReportProgress:
    stage: str
    current: int
    total: int
    message: str


Progress = Callable[[ReportProgress], None]


def _noop(_: ReportProgress) -> None:
    return None


def _slug(value: Any, index: int) -> str:
    text = "".join(
        character if character.isascii() and (character.isalnum() or character == "_") else "_"
        for character in str(value or "")
    ).strip("_").lower()
    return text or f"panel_{index + 1}"


async def plan_panels(
    session: AsyncSession, knowledge: dict[str, Any], question: str, locale: str
) -> tuple[dict[str, str], list[dict[str, str]]]:
    """Split the request into panels, each a standalone question.

    A failure here is not fatal: the whole request becomes a single panel, which is
    exactly the old single-query behaviour.
    """
    single = [{"key": "main", "question": question}]
    title = {"fa": question, "en": question}

    try:
        completion = await call_task(
            session,
            "plan_report",
            build_plan_messages(question, knowledge, locale),
            schema=PLAN_SCHEMA,
            max_attempts_per_model=1,
        )
        proposed = json.loads(completion.text)
    except Exception:  # noqa: BLE001 - planning is an optimisation, not a requirement
        return title, single

    if not isinstance(proposed, dict):
        return title, single

    proposed_title = proposed.get("title")
    if isinstance(proposed_title, dict) and (proposed_title.get("fa") or proposed_title.get("en")):
        title = {
            "fa": str(proposed_title.get("fa") or question),
            "en": str(proposed_title.get("en") or question),
        }

    panels: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, panel in enumerate(proposed.get("panels") or []):
        if not isinstance(panel, dict):
            continue
        text = str(panel.get("question") or "").strip()
        if not text:
            continue
        key = _slug(panel.get("key"), index)
        while key in seen:
            key = f"{key}_{len(seen)}"
        seen.add(key)
        panels.append({"key": key, "question": text})
        if len(panels) >= MAX_PANELS:
            break

    return title, panels or single


async def build_report(
    session: AsyncSession,
    report_id: UUID,
    knowledge: dict[str, Any],
    progress: Progress = _noop,
) -> Report:
    """Plan, answer, and design — recording every panel as a Query of its own.

    Each panel is saved as a Query so it appears in history and can be re-run
    without the model. A panel whose SQL fails is reported and skipped; the panels
    that worked still reach the user.
    """
    report = await session.get(Report, report_id)
    if report is None:
        raise LookupError(f"report {report_id} not found")

    source = await session.get(DataSource, report.data_source_id)
    if source is None:
        raise LookupError("source not found")

    report.status = ReportStatus.RUNNING
    await session.flush()

    question = report.question or ""
    locale = report.locale

    progress(ReportProgress("plan", 0, 1, question))
    title, panels = await plan_panels(session, knowledge, question, locale)
    report.title = title
    await session.flush()
    progress(ReportProgress("plan", 1, 1, title.get(locale) or title.get("en", "")))

    adapter = adapter_for(source.kind, decrypt_config(source))
    datasets: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []

    total = len(panels)
    for index, panel in enumerate(panels):
        progress(ReportProgress("query", index, total, panel["question"]))
        try:
            answer = await answer_question(
                session, adapter, knowledge, panel["question"], locale=locale, row_limit=1000
            )
        except QueryFailed as exc:
            session.add(
                Query(
                    data_source_id=report.data_source_id,
                    question=panel["question"],
                    locale=locale,
                    sql=exc.sql,
                    error=exc.message,
                    status=QueryStatus(exc.status),
                    created_by=report.created_by,
                )
            )
            await session.flush()
            failures.append({"panel": panel["key"], "error": exc.message})
            progress(ReportProgress("query", index + 1, total, exc.message))
            continue

        query = Query(
            data_source_id=report.data_source_id,
            question=answer.question,
            locale=locale,
            sql=answer.sql,
            explanation=answer.explanation,
            tables_used=answer.tables_used,
            assumptions=answer.assumptions,
            row_count=answer.row_count,
            duration_ms=answer.duration_ms,
            status=QueryStatus.SUCCEEDED,
            created_by=report.created_by,
        )
        session.add(query)
        await session.flush()

        datasets.append({
            "key": panel["key"],
            "query_id": str(query.id),
            "question": answer.question,
            "sql": answer.sql,
            "explanation": answer.explanation,
            "columns": answer.columns,
            "rows": answer.rows,
            "row_count": answer.row_count,
            # Arithmetic over the real rows, computed once. The designer narrates
            # from these rather than counting sample rows itself.
            "facts": describe_panel(answer.question, answer.columns, answer.rows),
        })
        progress(ReportProgress("query", index + 1, total, f"{answer.row_count} rows"))

    if not datasets:
        report.status = ReportStatus.FAILED
        report.error = json.dumps({"failures": failures}, ensure_ascii=False)
        await session.flush()
        progress(ReportProgress("design", 1, 1, "no panel could be answered"))
        return report

    # The first successful panel stays the report's primary query, so a report
    # still has one even for callers that only know about the old shape.
    report.query_id = UUID(datasets[0]["query_id"])

    progress(ReportProgress("design", 0, 1, "designing layout"))
    try:
        completion = await call_task(
            session,
            "design_report",
            build_report_messages(question, datasets, locale),
            schema=REPORT_SCHEMA,
            max_attempts_per_model=1,
        )
        spec = coerce_spec(json.loads(completion.text), datasets)
    except Exception:  # noqa: BLE001 - a plain layout beats losing the data
        spec = fallback_spec(title, datasets)

    # Rows are not stored: a report is a live view, re-run on each open. Only what
    # is needed to redraw it is kept.
    spec["datasets"] = [
        {
            "key": dataset["key"],
            "query_id": dataset["query_id"],
            "question": dataset["question"],
            "explanation": dataset["explanation"],
        }
        for dataset in datasets
    ]
    spec["title"] = spec.get("title") or title

    report.spec = spec
    report.title = spec["title"]
    report.status = ReportStatus.PARTIAL if failures else ReportStatus.SUCCEEDED
    report.error = json.dumps({"failures": failures}, ensure_ascii=False) if failures else None
    await session.flush()
    progress(ReportProgress("design", 1, 1, "done"))
    return report
