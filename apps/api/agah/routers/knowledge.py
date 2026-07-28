from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from agah.db import get_session
from agah.models.entity import Entity, EntityStatus
from agah.models.relationship import Relationship
from agah.models.source import DataSource
from agah.models.user import User
from agah.schemas.knowledge import (
    SCHEMA_VERSION,
    Bilingual,
    KnowledgeEntity,
    KnowledgeExport,
    KnowledgeField,
    KnowledgeSource,
)
from agah.security.deps import current_user

router = APIRouter(tags=["knowledge"])

DIALECTS = {"postgres": "postgres", "mysql": "mysql", "mssql": "tsql", "oracle": "oracle"}


def _merged(ai: dict[str, Any] | None, human: dict[str, Any] | None, key: str) -> Bilingual:
    ai_value = (ai or {}).get(key) or {}
    human_value = (human or {}).get(key) or {}
    return Bilingual(
        fa=human_value.get("fa") or ai_value.get("fa") or "",
        en=human_value.get("en") or ai_value.get("en") or "",
    )


@router.get("/api/sources/{source_id}/knowledge", response_model=KnowledgeExport)
async def export_knowledge(
    source_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
) -> KnowledgeExport:
    source = await session.get(DataSource, source_id)
    if source is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "source not found")

    entities = (
        await session.scalars(
            select(Entity)
            .where(
                Entity.data_source_id == source_id,
                Entity.status == EntityStatus.APPROVED,
            )
            .options(selectinload(Entity.fields))
            .order_by(Entity.schema_name, Entity.name)
        )
    ).all()
    approved_ids = {entity.id for entity in entities}

    relationships = (
        await session.scalars(
            select(Relationship).where(Relationship.data_source_id == source_id)
        )
    ).all()
    by_entity: dict[UUID, list[dict[str, Any]]] = {}
    names = {entity.id: entity.name for entity in entities}
    for relationship in relationships:
        # Both endpoints must be approved, so the export never references a table
        # it does not itself contain.
        if (
            relationship.from_entity_id not in approved_ids
            or relationship.to_entity_id not in approved_ids
        ):
            continue
        by_entity.setdefault(relationship.from_entity_id, []).append({
            "from": relationship.from_field,
            "to": f"{names[relationship.to_entity_id]}.{relationship.to_field}",
            "kind": str(relationship.kind),
            "cardinality": relationship.cardinality,
            "confidence": relationship.confidence,
        })

    exported = []
    for entity in entities:
        description = {**(entity.description_ai or {})}
        human = entity.description_human or {}
        exported.append(
            KnowledgeEntity(
                id=entity.id,
                kind=entity.kind,
                schema_name=entity.schema_name,
                name=entity.name,
                summary=_merged(entity.description_ai, human, "summary"),
                grain=human.get("grain") or description.get("grain"),
                business_domain=(
                    human.get("business_domain") or description.get("business_domain")
                ),
                row_count_approx=entity.row_count_approx,
                fields=[
                    KnowledgeField(
                        name=field.name,
                        type=field.data_type,
                        nullable=field.nullable,
                        meaning=Bilingual(
                            fa=(field.meaning_human or {}).get("fa")
                            or (field.meaning_ai or {}).get("fa")
                            or "",
                            en=(field.meaning_human or {}).get("en")
                            or (field.meaning_ai or {}).get("en")
                            or "",
                        ),
                        enum_map=field.enum_map,
                        unit=field.unit,
                        pii_class=str(field.pii_class),
                    )
                    for field in entity.fields
                ],
                relationships=by_entity.get(entity.id, []),
                sample_questions=(
                    human.get("common_questions") or description.get("common_questions") or []
                ),
            )
        )

    return KnowledgeExport(
        schema_version=SCHEMA_VERSION,
        source=KnowledgeSource(
            id=source.id,
            name=source.name,
            kind=str(source.kind),
            dialect=DIALECTS.get(str(source.kind), str(source.kind)),
        ),
        generated_at=datetime.now(UTC),
        entities=exported,
    )
