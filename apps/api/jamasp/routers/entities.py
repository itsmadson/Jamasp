from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Text, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from jamasp.db import get_session
from jamasp.models.entity import Entity, EntityStatus
from jamasp.models.user import User
from jamasp.schemas.entity import (
    BulkApproveRequest,
    BulkApproveResult,
    EntityListOut,
    EntityOut,
    EntityPatch,
    EntitySummaryOut,
)
from jamasp.security.deps import current_user, require_admin

router = APIRouter(tags=["entities"])

SORTS = {
    "name": Entity.name.asc(),
    "confidence_asc": Entity.confidence.asc().nulls_first(),
    "status": Entity.status.asc(),
}


async def _load(session: AsyncSession, entity_id: UUID) -> Entity:
    entity = (
        await session.scalars(
            select(Entity).where(Entity.id == entity_id).options(selectinload(Entity.fields))
        )
    ).one_or_none()
    if entity is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "entity not found")
    return entity


@router.get("/api/sources/{source_id}/entities", response_model=EntityListOut)
async def list_entities(
    source_id: UUID,
    status_filter: EntityStatus | None = Query(default=None, alias="status"),
    min_confidence: float | None = None,
    q: str | None = None,
    sort: str = "name",
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
) -> EntityListOut:
    conditions = [Entity.data_source_id == source_id]
    if status_filter is not None:
        conditions.append(Entity.status == status_filter)
    if min_confidence is not None:
        conditions.append(Entity.confidence >= min_confidence)
    if q:
        pattern = f"%{q}%"
        # Cast the JSONB description to text so Persian search hits summaries too.
        conditions.append(
            or_(
                Entity.name.ilike(pattern),
                cast(Entity.description_ai, Text).ilike(pattern),
            )
        )

    total = await session.scalar(select(func.count()).select_from(Entity).where(*conditions))
    rows = (
        await session.scalars(
            select(Entity)
            .where(*conditions)
            .order_by(SORTS.get(sort, SORTS["name"]))
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return EntityListOut(
        items=[EntitySummaryOut.model_validate(row) for row in rows], total=total or 0
    )


@router.get("/api/entities/{entity_id}", response_model=EntityOut)
async def get_entity(
    entity_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
) -> EntityOut:
    return EntityOut.model_validate(await _load(session, entity_id))


@router.patch("/api/entities/{entity_id}", response_model=EntityOut)
async def patch_entity(
    entity_id: UUID,
    payload: EntityPatch,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
) -> EntityOut:
    entity = await _load(session, entity_id)

    if payload.description_human is not None:
        # AI text is never overwritten: both versions stay, human wins on read.
        entity.description_human = payload.description_human

    if payload.fields:
        by_id = {field.id: field for field in entity.fields}
        for patch in payload.fields:
            field = by_id.get(patch.id)
            if field is None:
                raise HTTPException(
                    status.HTTP_404_NOT_FOUND, f"field {patch.id} not on this entity"
                )
            supplied = patch.model_dump(exclude_unset=True, exclude={"id"})
            for key, value in supplied.items():
                setattr(field, key, value)

    await session.flush()
    return EntityOut.model_validate(await _load(session, entity_id))


@router.post("/api/entities/{entity_id}/approve", response_model=EntityOut)
async def approve_entity(
    entity_id: UUID,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
) -> EntityOut:
    entity = await _load(session, entity_id)
    entity.status = EntityStatus.APPROVED
    entity.approved_by = admin.id
    entity.approved_at = datetime.now(UTC)
    await session.flush()
    return EntityOut.model_validate(entity)


@router.post("/api/entities/{entity_id}/ignore", response_model=EntityOut)
async def ignore_entity(
    entity_id: UUID,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
) -> EntityOut:
    entity = await _load(session, entity_id)
    entity.status = EntityStatus.IGNORED
    await session.flush()
    return EntityOut.model_validate(entity)


@router.post(
    "/api/sources/{source_id}/entities/bulk-approve", response_model=BulkApproveResult
)
async def bulk_approve(
    source_id: UUID,
    payload: BulkApproveRequest,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
) -> BulkApproveResult:
    rows = (
        await session.scalars(
            select(Entity).where(
                Entity.data_source_id == source_id,
                Entity.status.in_([EntityStatus.PENDING, EntityStatus.STALE]),
                Entity.confidence.is_not(None),
                Entity.confidence >= payload.min_confidence,
            )
        )
    ).all()

    now = datetime.now(UTC)
    for entity in rows:
        entity.status = EntityStatus.APPROVED
        entity.approved_by = admin.id
        entity.approved_at = now
    await session.flush()
    return BulkApproveResult(approved_count=len(rows))
