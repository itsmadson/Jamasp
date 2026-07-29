"""Sequences the five scan stages and owns all persistence decisions.

The rule that matters here: an entity whose structure did not change is never
touched. Its approval, its human-written description and its approval timestamp
survive every subsequent scan.
"""

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from agah.adapters.base import SourceAdapter
from agah.adapters.registry import adapter_for
from agah.models.entity import Entity, EntityStatus, Field
from agah.models.relationship import Relationship, RelationshipKind, RelationshipStatus
from agah.models.scan import Scan, ScanStatus
from agah.models.source import DataSource, SourceStatus
from agah.pipeline.describe import DescribeFailed, EntityDescription, describe_entity
from agah.pipeline.diff import SnapshotDiff, diff_snapshots
from agah.pipeline.embed import embed_entities
from agah.pipeline.probe import probe_relationships
from agah.pipeline.profile import EntityProfile, profile_entity
from agah.pipeline.snapshot import (
    ColumnInfo,
    EntitySnapshot,
    ForeignKeyInfo,
    Identity,
    StructuralSnapshot,
)
from agah.security.crypto import decrypt, key_from_settings

NEEDS_WORK = (EntityStatus.PENDING, EntityStatus.STALE, EntityStatus.DESCRIBE_FAILED)


@dataclass(frozen=True)
class ProgressEvent:
    stage: str
    current: int
    total: int
    message: str


ProgressSink = Callable[[ProgressEvent], None]


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _emit(sink: ProgressSink | None, stage: str, current: int, total: int, message: str) -> None:
    if sink is not None:
        sink(ProgressEvent(stage=stage, current=current, total=total, message=message))


def decrypt_config(source: DataSource) -> dict[str, Any]:
    return json.loads(decrypt(source.config_encrypted, key_from_settings()))


def _snapshot_from_json(payload: dict[str, Any] | None) -> StructuralSnapshot | None:
    if not payload:
        return None
    entities = []
    for entity in payload.get("entities", []):
        entities.append(
            EntitySnapshot(
                kind=entity["kind"],
                schema_name=entity["schema_name"],
                name=entity["name"],
                columns=tuple(ColumnInfo(**column) for column in entity["columns"]),
                foreign_keys=tuple(
                    ForeignKeyInfo(
                        from_columns=tuple(fk["from_columns"]),
                        to_schema=fk["to_schema"],
                        to_table=fk["to_table"],
                        to_columns=tuple(fk["to_columns"]),
                    )
                    for fk in entity.get("foreign_keys", [])
                ),
                unique_constraints=tuple(
                    tuple(constraint) for constraint in entity.get("unique_constraints", [])
                ),
                indexes=tuple(entity.get("indexes", [])),
                comment=entity.get("comment"),
                row_count_approx=entity.get("row_count_approx"),
            )
        )
    return StructuralSnapshot(dialect=payload["dialect"], entities=tuple(entities))


async def _load_previous_snapshot(
    session: AsyncSession, source_id: UUID, exclude: UUID
) -> StructuralSnapshot | None:
    row = (
        await session.scalars(
            select(Scan)
            .where(
                Scan.data_source_id == source_id,
                Scan.id != exclude,
                Scan.structural_snapshot.is_not(None),
            )
            .order_by(Scan.created_at.desc())
            .limit(1)
        )
    ).one_or_none()
    return _snapshot_from_json(row.structural_snapshot) if row else None


async def _upsert_entities(
    session: AsyncSession,
    source: DataSource,
    snapshot: StructuralSnapshot,
    delta: SnapshotDiff,
) -> dict[Identity, Entity]:
    existing = {
        (entity.schema_name, entity.name): entity
        for entity in (
            await session.scalars(
                select(Entity)
                .where(Entity.data_source_id == source.id)
                .options(selectinload(Entity.fields))
            )
        ).all()
    }
    changed = {change.identity for change in delta.changed}
    unchanged = set(delta.unchanged)
    result: dict[Identity, Entity] = {}

    for identity, entity_snapshot in snapshot.by_identity().items():
        if identity in unchanged and identity in existing:
            # Deliberately untouched: this is what preserves human approval.
            result[identity] = existing[identity]
            continue

        entity = existing.get(identity)
        structural = asdict(entity_snapshot)
        structural_hash = snapshot.hash_for(entity_snapshot)

        if entity is None:
            entity = Entity(
                data_source_id=source.id,
                kind=entity_snapshot.kind,
                schema_name=entity_snapshot.schema_name,
                name=entity_snapshot.name,
                structural=structural,
                structural_hash=structural_hash,
                status=EntityStatus.PENDING,
                row_count_approx=entity_snapshot.row_count_approx,
            )
            session.add(entity)
        else:
            entity.structural = structural
            entity.structural_hash = structural_hash
            entity.row_count_approx = entity_snapshot.row_count_approx
            if identity in changed:
                entity.status = EntityStatus.STALE
                entity.version += 1

        await session.flush()
        await _sync_fields(session, entity, entity_snapshot)
        result[identity] = entity

    return result


async def _load_fields(session: AsyncSession, entity: Entity) -> list[Field]:
    """Explicit query: the relationship would lazy-load, which async forbids."""
    return list(
        (await session.scalars(select(Field).where(Field.entity_id == entity.id))).all()
    )


async def _sync_fields(
    session: AsyncSession, entity: Entity, entity_snapshot: EntitySnapshot
) -> None:
    existing = {field.name: field for field in await _load_fields(session, entity)}
    seen: set[str] = set()

    for column in entity_snapshot.columns:
        seen.add(column.name)
        field = existing.get(column.name)
        if field is None:
            session.add(
                Field(
                    entity_id=entity.id,
                    name=column.name,
                    data_type=column.data_type,
                    nullable=column.nullable,
                    is_pk=column.is_pk,
                    ordinal=column.ordinal,
                )
            )
        else:
            field.data_type = column.data_type
            field.nullable = column.nullable
            field.is_pk = column.is_pk
            field.ordinal = column.ordinal

    for name, field in existing.items():
        if name not in seen:
            await session.delete(field)
    await session.flush()


def _jsonable(value: Any) -> Any:
    """Dates, Decimals and UUIDs come back from drivers as native objects; JSONB
    only takes primitives, so anything exotic is stored as its string form."""
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]
    return str(value)


async def _apply_profile(session: AsyncSession, entity: Entity, profile: EntityProfile) -> None:
    by_name = {column.name: column for column in profile.columns}
    for field in await _load_fields(session, entity):
        column = by_name.get(field.name)
        if column is None:
            continue
        field.pii_class = column.pii_class
        field.stats = {
            "distinct_count": column.distinct_count,
            "null_ratio": column.null_ratio,
            "min_value": _jsonable(column.min_value),
            "max_value": _jsonable(column.max_value),
            "sample_values": _jsonable(column.sample_values),
        }
    entity.row_count_approx = profile.row_count
    await session.flush()


async def _persist_relationships(
    session: AsyncSession,
    source: DataSource,
    snapshot: StructuralSnapshot,
    entities: dict[Identity, Entity],
    candidates: list[Any],
) -> None:
    await session.execute(
        Relationship.__table__.delete().where(Relationship.data_source_id == source.id)
    )

    for entity_snapshot in snapshot.entities:
        entity = entities.get(entity_snapshot.identity)
        if entity is None:
            continue
        for foreign_key in entity_snapshot.foreign_keys:
            target = entities.get((foreign_key.to_schema, foreign_key.to_table))
            if target is None:
                continue
            session.add(
                Relationship(
                    data_source_id=source.id,
                    from_entity_id=entity.id,
                    from_field=foreign_key.from_columns[0],
                    to_entity_id=target.id,
                    to_field=foreign_key.to_columns[0],
                    kind=RelationshipKind.DECLARED,
                    cardinality="many_to_one",
                    confidence=1.0,
                    status=RelationshipStatus.APPROVED,
                )
            )

    for candidate in candidates:
        source_entity = entities.get(candidate.from_identity)
        target_entity = entities.get(candidate.to_identity)
        if source_entity is None or target_entity is None:
            continue
        session.add(
            Relationship(
                data_source_id=source.id,
                from_entity_id=source_entity.id,
                from_field=candidate.from_column,
                to_entity_id=target_entity.id,
                to_field=candidate.to_column,
                kind=RelationshipKind.INFERRED,
                cardinality="many_to_one",
                confidence=candidate.confidence,
                evidence={
                    "hit_rate": candidate.hit_rate,
                    "distinct_source_values": candidate.distinct_source_values,
                },
                status=RelationshipStatus.PENDING,
            )
        )
    await session.flush()


def _apply_description(
    entity: Entity, fields: list[Field], description: EntityDescription
) -> None:
    entity.description_ai = description.to_json()
    entity.confidence = description.confidence
    by_name = {field["name"]: field for field in description.fields}
    for field in fields:
        described = by_name.get(field.name)
        if described is None:
            continue
        field.meaning_ai = described.get("meaning")
        field.enum_map = described.get("enum_map")
        field.unit = described.get("unit")
        field.confidence = described.get("confidence")


def _neighbors(snapshot: StructuralSnapshot, entity_snapshot: EntitySnapshot) -> list[
    EntitySnapshot
]:
    wanted = {
        (foreign_key.to_schema, foreign_key.to_table)
        for foreign_key in entity_snapshot.foreign_keys
    }
    by_identity = snapshot.by_identity()
    return [by_identity[identity] for identity in wanted if identity in by_identity]


async def _scan_stats(session: AsyncSession, scan_id: UUID) -> dict[str, Any]:
    from agah.models.observability import LLMCall

    calls = (await session.scalars(select(LLMCall).where(LLMCall.scan_id == scan_id))).all()
    return {
        "llm_calls": len(calls),
        "tokens_in": sum(call.tokens_in for call in calls),
        "tokens_out": sum(call.tokens_out for call in calls),
    }


async def run_scan(
    session: AsyncSession, scan_id: UUID, progress: ProgressSink | None = None
) -> Scan:
    scan = await session.get(Scan, scan_id)
    if scan is None:
        raise LookupError(f"scan {scan_id} not found")
    source = await session.get(DataSource, scan.data_source_id)
    if source is None:
        raise LookupError(f"data source {scan.data_source_id} not found")

    adapter: SourceAdapter = adapter_for(source.kind, decrypt_config(source))
    scan.status = ScanStatus.RUNNING
    scan.started_at = _utcnow()
    source.status = SourceStatus.SCANNING
    await session.flush()

    failures: list[dict[str, str]] = []

    try:
        _emit(progress, "introspect", 0, 1, "reading schema")
        snapshot = await adapter.introspect()
        scan.structural_snapshot = snapshot.to_json()
        await session.flush()

        previous = await _load_previous_snapshot(session, source.id, exclude=scan.id)
        delta = diff_snapshots(previous, snapshot)
        entities = await _upsert_entities(session, source, snapshot, delta)

        by_identity = snapshot.by_identity()
        todo = [
            (identity, entity)
            for identity, entity in entities.items()
            if entity.status in NEEDS_WORK
        ]

        profiles = {}
        for index, (identity, entity) in enumerate(todo):
            _emit(progress, "profile", index, len(todo), entity.name)
            profile = await profile_entity(
                adapter, by_identity[identity], source.sampling_policy
            )
            profiles[identity] = profile
            # The classification has to reach the stored field: the review UI and
            # the knowledge export both read it, and defaulting to "none" would
            # tell a reviewer a national ID column holds no personal data.
            await _apply_profile(session, entity, profile)

        _emit(progress, "probe", 0, 1, "inferring relationships")
        candidates = await probe_relationships(adapter, snapshot)
        await _persist_relationships(session, source, snapshot, entities, candidates)

        for index, (identity, entity) in enumerate(todo):
            _emit(progress, "describe", index, len(todo), entity.name)
            try:
                description = await describe_entity(
                    session,
                    by_identity[identity],
                    profiles[identity],
                    _neighbors(snapshot, by_identity[identity]),
                    scan.id,
                )
            except DescribeFailed as exc:
                entity.status = EntityStatus.DESCRIBE_FAILED
                failures.append({"entity": entity.name, "error": str(exc)})
                await session.flush()
                continue
            _apply_description(entity, await _load_fields(session, entity), description)
            # STALE must survive re-description: it tells the reviewer this entity
            # changed and carries the structural diff. Only a failed describe that
            # now succeeded gets promoted back to PENDING.
            if entity.status is EntityStatus.DESCRIBE_FAILED:
                entity.status = EntityStatus.PENDING
            await session.flush()

        _emit(progress, "embed", 0, 1, "indexing descriptions")
        describable = [
            entity for _, entity in todo if entity.status is not EntityStatus.DESCRIBE_FAILED
        ]
        try:
            await embed_entities(
                session,
                [(entity, await _load_fields(session, entity)) for entity in describable],
                scan.id,
            )
        except Exception as exc:  # noqa: BLE001 - degrade, never discard the descriptions
            # Embeddings only speed up table retrieval for the query engine. A
            # deployment with no embedding service is a normal state, and the
            # descriptions this scan just paid for stay valid without them.
            failures.append({"stage": "embed", "error": str(exc)})

        _emit(progress, "diff", 0, 1, "finalizing")
        for identity in delta.removed:
            archived = entities.get(identity)
            if archived is not None:
                archived.status = EntityStatus.ARCHIVED

        scan.status = ScanStatus.PARTIAL if failures else ScanStatus.SUCCEEDED
        scan.error = {"failures": failures} if failures else None
        source.status = SourceStatus.READY
        source.last_scan_at = _utcnow()
    except Exception as exc:
        scan.status = ScanStatus.FAILED
        scan.error = {"fatal": str(exc)}
        source.status = SourceStatus.ERROR
        scan.finished_at = _utcnow()
        await session.commit()
        raise
    else:
        scan.finished_at = _utcnow()
        scan.stats = await _scan_stats(session, scan.id)
        await session.commit()

    return scan
