import json
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jamasp.adapters.registry import adapter_for
from jamasp.config import get_settings
from jamasp.db import get_session
from jamasp.models.query import Query
from jamasp.models.report import Report, ReportStatus
from jamasp.models.source import DataSource
from jamasp.models.user import User
from jamasp.pipeline.orchestrator import decrypt_config
from jamasp.pipeline.worker import report_channel
from jamasp.query.pipeline import infer_columns
from jamasp.queue import get_queue
from jamasp.report.edit import EditRejected, edit_report_spec
from jamasp.report.insights import describe_panel, narrative_for
from jamasp.security.deps import current_user

router = APIRouter(tags=["reports"])


def get_report_progress_source():
    """The Redis connection the SSE stream listens on. Overridden in tests."""
    from redis.asyncio import Redis

    return Redis.from_url(get_settings().redis_url)


class CreateReportRequest(BaseModel):
    question: str
    locale: str = "fa"
    row_limit: int = 1000


class EditReportRequest(BaseModel):
    instruction: str
    locale: str = "fa"


class ReportSummaryOut(BaseModel):
    id: UUID
    data_source_id: UUID
    title: dict[str, str]
    locale: str
    created_at: datetime


class DatasetOut(BaseModel):
    key: str
    question: str | None = None
    sql: str | None = None
    explanation: dict[str, str] | None = None
    columns: list[dict[str, str]] = []
    rows: list[dict[str, Any]] = []
    row_count: int = 0
    error: str | None = None
    # Recomputed on every read, never stored: a report re-runs its SQL, so stored
    # facts would drift from the rows shown beside them.
    facts: dict[str, Any] = {}
    narrative: dict[str, str] = {}


class ReportOut(ReportSummaryOut):
    status: str = "succeeded"
    error: str | None = None
    question: str | None = None
    spec: dict[str, Any]
    datasets: list[DatasetOut] = []
    # The first panel, repeated flat. Kept so a caller that predates multi-panel
    # reports still finds what it expects.
    sql: str | None = None
    explanation: dict[str, str] | None = None
    columns: list[dict[str, str]] = []
    rows: list[dict[str, Any]] = []
    row_count: int = 0


@router.post(
    "/api/sources/{source_id}/reports",
    response_model=ReportOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_report(
    source_id: UUID,
    payload: CreateReportRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
    queue=Depends(get_queue),
) -> ReportOut:
    """Queue the build and answer immediately.

    Building takes several model calls. Answering only when it finishes means the
    browser gives up first and shows an error for work that actually succeeded, so
    the report is created empty and filled in by the worker while the client
    follows /events.
    """
    source = await session.get(DataSource, source_id)
    if source is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "source not found")

    title = {"fa": payload.question, "en": payload.question}
    report = Report(
        data_source_id=source_id,
        question=payload.question,
        locale=payload.locale,
        title=title,
        spec={"schema_version": "2.0", "title": title, "summary": {"fa": "", "en": ""},
              "blocks": [], "datasets": []},
        status=ReportStatus.QUEUED,
        created_by=user.id,
    )
    session.add(report)
    await session.flush()
    await queue.enqueue_job("report_task", str(report.id))

    return ReportOut(
        id=report.id,
        data_source_id=source_id,
        title=title,
        locale=payload.locale,
        created_at=report.created_at,
        status=report.status.value,
        question=payload.question,
        spec=report.spec,
    )


@router.get("/api/sources/{source_id}/reports", response_model=list[ReportSummaryOut])
async def list_reports(
    source_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
) -> list[ReportSummaryOut]:
    rows = (
        await session.scalars(
            select(Report)
            .where(Report.data_source_id == source_id)
            .order_by(Report.created_at.desc())
        )
    ).all()
    return [
        ReportSummaryOut(
            id=row.id,
            data_source_id=row.data_source_id,
            title=row.title,
            locale=row.locale,
            created_at=row.created_at,
        )
        for row in rows
    ]


async def _run_dataset(
    adapter: Any, entry: dict[str, Any], query: Query | None
) -> DatasetOut:
    """Re-run one panel. A panel that fails reports its own error, not the page's."""
    dataset = DatasetOut(
        key=entry.get("key", "main"),
        question=entry.get("question") or (query.question if query else None),
        sql=query.sql if query else None,
        explanation=entry.get("explanation") or (query.explanation if query else None),
    )
    if adapter is None or query is None or not query.sql:
        return dataset

    try:
        raw = await adapter.execute_readonly(query.sql, limit=1000)
    except Exception as exc:  # noqa: BLE001 - one dead panel must not blank the report
        dataset.error = str(exc)
        return dataset

    dataset.rows = [
        {
            key: (value if isinstance(value, str | int | float | bool | type(None)) else str(value))
            for key, value in row.items()
        }
        for row in raw
    ]
    dataset.columns = infer_columns(dataset.rows)
    dataset.row_count = len(dataset.rows)
    dataset.facts = describe_panel(dataset.question, dataset.columns, dataset.rows)
    dataset.narrative = narrative_for(dataset.facts)
    return dataset


@router.get("/api/reports/{report_id}", response_model=ReportOut)
async def get_report(
    report_id: UUID,
    refresh: bool = True,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
) -> ReportOut:
    """Re-runs each panel's saved SQL by default: a report is a live view.

    The model is never consulted again — the layout is already decided.
    """
    report = await session.get(Report, report_id)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "report not found")

    spec = report.spec or {}
    entries = list(spec.get("datasets") or [])
    if not entries and report.query_id:
        # A report from before panels existed: its single query is panel "main".
        entries = [{"key": "main", "query_id": str(report.query_id)}]

    adapter = None
    if refresh:
        source = await session.get(DataSource, report.data_source_id)
        if source is not None:
            adapter = adapter_for(source.kind, decrypt_config(source))

    datasets: list[DatasetOut] = []
    for entry in entries:
        query = None
        raw_id = entry.get("query_id")
        if raw_id:
            query = await session.get(Query, UUID(str(raw_id)))
        datasets.append(await _run_dataset(adapter, entry, query))

    first = datasets[0] if datasets else DatasetOut(key="main")
    return ReportOut(
        id=report.id,
        data_source_id=report.data_source_id,
        title=report.title,
        locale=report.locale,
        created_at=report.created_at,
        status=report.status.value,
        error=report.error,
        question=report.question,
        spec=spec,
        datasets=datasets,
        sql=first.sql,
        explanation=first.explanation,
        columns=first.columns,
        rows=first.rows,
        row_count=first.row_count,
    )


@router.get("/api/reports/{report_id}/events")
async def report_events(
    report_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
    progress_source=Depends(get_report_progress_source),
) -> StreamingResponse:
    """Stream the build's steps, so the wait shows what is happening."""
    report = await session.get(Report, report_id)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "report not found")

    async def stream() -> AsyncIterator[str]:
        # Current state first, so a client attaching late is never blank.
        yield f"data: {json.dumps({'stage': 'status', 'status': report.status.value})}\n\n"
        if report.status in {ReportStatus.SUCCEEDED, ReportStatus.PARTIAL, ReportStatus.FAILED}:
            yield f"data: {json.dumps({'stage': 'done', 'status': report.status.value})}\n\n"
            return

        pubsub = progress_source.pubsub()
        await pubsub.subscribe(report_channel(report_id))
        try:
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                data = message["data"]
                if isinstance(data, bytes):
                    data = data.decode()
                yield f"data: {data}\n\n"
                if json.loads(data).get("stage") == "done":
                    break
        finally:
            await pubsub.unsubscribe(report_channel(report_id))

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/api/reports/{report_id}/chat", response_model=ReportOut)
async def chat_edit_report(
    report_id: UUID,
    payload: EditReportRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
) -> ReportOut:
    """Change a report by describing the change.

    The edit is validated by the same rules that guard generation, and a rejected
    edit leaves the stored layout untouched.
    """
    current = await get_report(report_id, refresh=True, session=session, user=user)
    datasets = [
        {
            "key": dataset.key,
            "question": dataset.question,
            "columns": dataset.columns,
            "row_count": dataset.row_count,
        }
        for dataset in current.datasets
    ]

    try:
        updated = await edit_report_spec(
            session,
            current.spec,
            datasets,
            payload.instruction,
            locale=payload.locale,
        )
    except EditRejected as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {"status": "edit_rejected", "message": str(exc), "sql": None},
        ) from exc

    report = await session.get(Report, report_id)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "report not found")
    # The panel list is ours, not the model's: an edit changes presentation.
    updated["datasets"] = (report.spec or {}).get("datasets") or []
    report.spec = updated
    report.title = updated["title"]
    await session.flush()

    return ReportOut(
        id=report.id,
        data_source_id=report.data_source_id,
        title=updated["title"],
        locale=report.locale,
        created_at=report.created_at,
        status=report.status.value,
        question=report.question,
        spec=updated,
        datasets=current.datasets,
        sql=current.sql,
        explanation=current.explanation,
        columns=current.columns,
        rows=current.rows,
        row_count=current.row_count,
    )
