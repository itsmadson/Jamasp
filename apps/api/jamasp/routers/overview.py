"""One request that answers "where is everything up to?".

The dashboard needs counts per source, the newest scan, and recent activity. Asking
for those separately is a request per source and a waterfall the user watches, so
they are aggregated here instead.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from jamasp.db import get_session
from jamasp.models.entity import Entity, EntityStatus
from jamasp.models.query import Query
from jamasp.models.report import Report
from jamasp.models.scan import Scan
from jamasp.models.source import DataSource
from jamasp.models.user import User
from jamasp.security.deps import current_user

router = APIRouter(tags=["overview"])


class SourceProgress(BaseModel):
    """Where one source sits in the scan → review → ask journey."""

    id: UUID
    name: str
    kind: str
    status: str
    last_scan_at: datetime | None = None
    last_scan_status: str | None = None
    entities_total: int = 0
    entities_approved: int = 0
    entities_pending: int = 0
    reports: int = 0
    questions: int = 0
    # What this source needs from the user next, if anything.
    next_step: str = "scan"


class ActivityItem(BaseModel):
    kind: str
    id: UUID
    data_source_id: UUID
    title: str
    status: str
    created_at: datetime


class OverviewOut(BaseModel):
    sources: list[SourceProgress]
    recent: list[ActivityItem]
    totals: dict[str, int]


def _next_step(
    status: str, total: int, pending: int, approved: int, questions: int
) -> str:
    """The single thing to do next.

    A dashboard that shows five equal calls to action tells the user nothing about
    order, which is exactly the confusion this is meant to remove.
    """
    if status == "scanning":
        return "scanning"
    if total == 0:
        return "scan"
    if pending > 0:
        return "review"
    if approved == 0:
        return "review"
    if questions == 0:
        return "ask"
    return "ready"


@router.get("/api/overview", response_model=OverviewOut)
async def overview(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
) -> OverviewOut:
    sources = (
        await session.scalars(select(DataSource).order_by(DataSource.created_at.desc()))
    ).all()

    # Grouped counts, so the cost does not grow with the number of sources.
    entity_counts: dict[tuple[UUID, EntityStatus], int] = {
        (row.data_source_id, row.status): row.total
        for row in await session.execute(
            select(
                Entity.data_source_id,
                Entity.status,
                func.count().label("total"),
            ).group_by(Entity.data_source_id, Entity.status)
        )
    }
    report_counts = {
        row.data_source_id: row.total
        for row in await session.execute(
            select(Report.data_source_id, func.count().label("total")).group_by(
                Report.data_source_id
            )
        )
    }
    query_counts = {
        row.data_source_id: row.total
        for row in await session.execute(
            select(Query.data_source_id, func.count().label("total")).group_by(
                Query.data_source_id
            )
        )
    }
    latest_scans = {
        row.data_source_id: row
        for row in (
            await session.scalars(select(Scan).order_by(Scan.created_at.asc()))
        ).all()
    }

    progress: list[SourceProgress] = []
    for source in sources:
        counts = {
            status: entity_counts.get((source.id, status), 0) for status in EntityStatus
        }
        total = sum(
            count
            for status, count in counts.items()
            if status is not EntityStatus.ARCHIVED
        )
        approved = counts.get(EntityStatus.APPROVED, 0)
        pending = counts.get(EntityStatus.PENDING, 0) + counts.get(EntityStatus.STALE, 0)
        questions = query_counts.get(source.id, 0)
        scan = latest_scans.get(source.id)

        progress.append(
            SourceProgress(
                id=source.id,
                name=source.name,
                kind=source.kind.value,
                status=source.status.value,
                last_scan_at=scan.finished_at if scan else source.last_scan_at,
                last_scan_status=scan.status.value if scan else None,
                entities_total=total,
                entities_approved=approved,
                entities_pending=pending,
                reports=report_counts.get(source.id, 0),
                questions=questions,
                next_step=_next_step(
                    source.status.value, total, pending, approved, questions
                ),
            )
        )

    recent_queries = (
        await session.scalars(select(Query).order_by(Query.created_at.desc()).limit(8))
    ).all()
    recent_reports = (
        await session.scalars(select(Report).order_by(Report.created_at.desc()).limit(8))
    ).all()

    recent: list[ActivityItem] = [
        ActivityItem(
            kind="question",
            id=row.id,
            data_source_id=row.data_source_id,
            title=row.question,
            status=row.status.value,
            created_at=row.created_at,
        )
        for row in recent_queries
    ] + [
        ActivityItem(
            kind="report",
            id=row.id,
            data_source_id=row.data_source_id,
            title=_title_of(row),
            status=row.status.value,
            created_at=row.created_at,
        )
        for row in recent_reports
    ]
    recent.sort(key=lambda item: item.created_at, reverse=True)

    return OverviewOut(
        sources=progress,
        recent=recent[:10],
        totals={
            "sources": len(sources),
            "entities": sum(item.entities_total for item in progress),
            "approved": sum(item.entities_approved for item in progress),
            "pending": sum(item.entities_pending for item in progress),
            "reports": sum(item.reports for item in progress),
            "questions": sum(item.questions for item in progress),
        },
    )


def _title_of(report: Report) -> str:
    title: dict[str, Any] = report.title or {}
    return str(title.get("fa") or title.get("en") or report.question or "")
