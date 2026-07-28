"""Stage 4: index descriptions so the query engine can select relevant tables.

A 200-table schema does not fit in a prompt. S2 will retrieve the handful of tables
a question touches; that retrieval needs these vectors, and building them during the
scan avoids reprocessing every description later.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from agah.llm.router import build_provider, load_provider_config, load_route
from agah.models.entity import EMBEDDING_DIM, Entity, Field


async def embed_texts(
    session: AsyncSession, texts: list[str], scan_id: UUID | None = None
) -> list[list[float]]:
    if not texts:
        return []
    route = await load_route(session, "embed")
    providers = await load_provider_config(session)
    provider = build_provider(route.provider, providers.get(route.provider, {}))
    return await provider.embed(texts, model=route.model)


def embedding_text(entity: Entity, fields: list[Field]) -> str:
    """Both languages in one vector, so a Persian question matches an English description."""
    description = {**(entity.description_ai or {}), **(entity.description_human or {})}
    summary = description.get("summary") or {}
    parts = [
        entity.name,
        summary.get("fa", ""),
        summary.get("en", ""),
        description.get("grain", "") or "",
        " ".join(description.get("common_questions", []) or []),
        " ".join(
            f"{field.name} {(field.meaning_ai or {}).get('fa', '')} "
            f"{(field.meaning_ai or {}).get('en', '')}"
            for field in fields
        ),
    ]
    return "\n".join(part for part in parts if part)


async def embed_entities(
    session: AsyncSession,
    entities: list[tuple[Entity, list[Field]]],
    scan_id: UUID | None = None,
) -> None:
    if not entities:
        return
    vectors = await embed_texts(
        session, [embedding_text(entity, fields) for entity, fields in entities], scan_id
    )
    for (entity, _), vector in zip(entities, vectors, strict=False):
        if len(vector) == EMBEDDING_DIM:
            entity.embedding = vector
