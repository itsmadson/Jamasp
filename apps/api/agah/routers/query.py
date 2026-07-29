import json
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from agah.adapters.registry import adapter_for
from agah.db import get_session
from agah.models.query import Query, QueryStatus
from agah.models.source import DataSource
from agah.models.user import User
from agah.pipeline.orchestrator import decrypt_config
from agah.query.pipeline import QueryFailed, answer_question
from agah.routers.knowledge import export_knowledge
from agah.security.deps import current_user

router = APIRouter(tags=["query"])


class AskRequest(BaseModel):
    question: str
    locale: str = "fa"
    row_limit: int = 1000


class AskResponse(BaseModel):
    id: UUID
    question: str
    sql: str
    explanation: dict[str, str]
    tables_used: list[str]
    assumptions: list[str]
    columns: list[dict[str, str]]
    rows: list[dict[str, Any]]
    row_count: int
    duration_ms: int


@router.post("/api/sources/{source_id}/query", response_model=AskResponse)
async def ask(
    source_id: UUID,
    payload: AskRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
) -> AskResponse:
    source = await session.get(DataSource, source_id)
    if source is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "source not found")

    # Only human-approved knowledge is ever used, which is what makes the S1
    # review gate load-bearing rather than decorative.
    knowledge = json.loads(
        (await export_knowledge(source_id, session, user)).model_dump_json()
    )
    adapter = adapter_for(source.kind, decrypt_config(source))

    record = Query(
        data_source_id=source_id,
        question=payload.question,
        locale=payload.locale,
        created_by=user.id,
        status=QueryStatus.SUCCEEDED,
    )

    try:
        result = await answer_question(
            session,
            adapter,
            knowledge,
            payload.question,
            locale=payload.locale,
            row_limit=payload.row_limit,
        )
    except QueryFailed as exc:
        record.status = QueryStatus(exc.status)
        record.sql = exc.sql
        record.error = exc.message
        session.add(record)
        await session.flush()
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {"status": exc.status, "message": exc.message, "sql": exc.sql},
        ) from exc

    record.sql = result.sql
    record.explanation = result.explanation
    record.tables_used = result.tables_used
    record.assumptions = result.assumptions
    record.row_count = result.row_count
    record.duration_ms = result.duration_ms
    session.add(record)
    await session.flush()

    return AskResponse(
        id=record.id,
        question=result.question,
        sql=result.sql,
        explanation=result.explanation,
        tables_used=result.tables_used,
        assumptions=result.assumptions,
        columns=result.columns,
        rows=result.rows,
        row_count=result.row_count,
        duration_ms=result.duration_ms,
    )
