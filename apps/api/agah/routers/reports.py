import json
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agah.adapters.registry import adapter_for
from agah.db import get_session
from agah.models.query import Query, QueryStatus
from agah.models.report import Report
from agah.models.source import DataSource
from agah.models.user import User
from agah.pipeline.orchestrator import decrypt_config
from agah.query.pipeline import QueryFailed, answer_question, infer_columns
from agah.report.generate import design_report
from agah.routers.knowledge import export_knowledge
from agah.security.deps import current_user

router = APIRouter(tags=["reports"])


class CreateReportRequest(BaseModel):
    question: str
    locale: str = "fa"
    row_limit: int = 1000


class ReportSummaryOut(BaseModel):
    id: UUID
    data_source_id: UUID
    title: dict[str, str]
    locale: str
    created_at: datetime


class ReportOut(ReportSummaryOut):
    spec: dict[str, Any]
    sql: str | None = None
    explanation: dict[str, str] | None = None
    columns: list[dict[str, str]] = []
    rows: list[dict[str, Any]] = []
    row_count: int = 0


@router.post(
    "/api/sources/{source_id}/reports",
    response_model=ReportOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_report(
    source_id: UUID,
    payload: CreateReportRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
) -> ReportOut:
    source = await session.get(DataSource, source_id)
    if source is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "source not found")

    knowledge = json.loads(
        (await export_knowledge(source_id, session, user)).model_dump_json()
    )
    adapter = adapter_for(source.kind, decrypt_config(source))

    try:
        answer = await answer_question(
            session, adapter, knowledge, payload.question,
            locale=payload.locale, row_limit=payload.row_limit,
        )
    except QueryFailed as exc:
        session.add(
            Query(
                data_source_id=source_id, question=payload.question, locale=payload.locale,
                sql=exc.sql, error=exc.message, status=QueryStatus(exc.status),
                created_by=user.id,
            )
        )
        await session.flush()
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {"status": exc.status, "message": exc.message, "sql": exc.sql},
        ) from exc

    query = Query(
        data_source_id=source_id,
        question=answer.question,
        locale=payload.locale,
        sql=answer.sql,
        explanation=answer.explanation,
        tables_used=answer.tables_used,
        assumptions=answer.assumptions,
        row_count=answer.row_count,
        duration_ms=answer.duration_ms,
        status=QueryStatus.SUCCEEDED,
        created_by=user.id,
    )
    session.add(query)
    await session.flush()

    spec = await design_report(session, answer, locale=payload.locale)

    report = Report(
        data_source_id=source_id,
        query_id=query.id,
        title=spec["title"],
        spec=spec,
        locale=payload.locale,
        created_by=user.id,
    )
    session.add(report)
    await session.flush()

    return ReportOut(
        id=report.id,
        data_source_id=source_id,
        title=spec["title"],
        locale=payload.locale,
        created_at=report.created_at,
        spec=spec,
        sql=answer.sql,
        explanation=answer.explanation,
        columns=answer.columns,
        rows=answer.rows,
        row_count=answer.row_count,
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


@router.get("/api/reports/{report_id}", response_model=ReportOut)
async def get_report(
    report_id: UUID,
    refresh: bool = True,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
) -> ReportOut:
    """Re-runs the saved SQL by default: a report is a live view, not a snapshot.

    The model is never consulted again — the layout is already decided.
    """
    report = await session.get(Report, report_id)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "report not found")

    query = await session.get(Query, report.query_id) if report.query_id else None
    columns: list[dict[str, str]] = []
    rows: list[dict[str, Any]] = []

    if refresh and query is not None and query.sql:
        source = await session.get(DataSource, report.data_source_id)
        if source is not None:
            adapter = adapter_for(source.kind, decrypt_config(source))
            try:
                raw = await adapter.execute_readonly(query.sql, limit=1000)
                rows = [
                    {
                        key: (value if isinstance(value, str | int | float | bool | type(None))
                              else str(value))
                        for key, value in row.items()
                    }
                    for row in raw
                ]
                columns = infer_columns(rows)
            except Exception:  # noqa: BLE001 - a stale report still shows its layout
                columns, rows = [], []

    return ReportOut(
        id=report.id,
        data_source_id=report.data_source_id,
        title=report.title,
        locale=report.locale,
        created_at=report.created_at,
        spec=report.spec,
        sql=query.sql if query else None,
        explanation=query.explanation if query else None,
        columns=columns,
        rows=rows,
        row_count=len(rows),
    )
