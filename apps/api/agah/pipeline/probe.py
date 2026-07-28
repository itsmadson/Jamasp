"""Stage 2b: find relationships the schema never declared.

Databases in the target market frequently have no foreign keys at all, which leaves
the query generator unable to join. Candidates come from naming and type heuristics;
each is then tested with a bounded read-only containment query, so what gets recorded
is measured evidence rather than a guess.
"""

import re
from dataclasses import dataclass

from agah.adapters.base import SourceAdapter
from agah.pipeline.snapshot import EntitySnapshot, Identity, StructuralSnapshot

INTEGER_TYPES = ("integer", "bigint", "smallint", "serial", "bigserial", "numeric")


@dataclass(frozen=True)
class CandidateRelationship:
    from_identity: Identity
    from_column: str
    to_identity: Identity
    to_column: str
    hit_rate: float
    distinct_source_values: int
    confidence: float


def _is_integer(data_type: str) -> bool:
    lowered = data_type.lower()
    return any(lowered.startswith(candidate) for candidate in INTEGER_TYPES)


def _stem(column: str) -> str:
    return re.sub(r"_?(id|code|key|no)$", "", column.lower()).strip("_")


def _singularize(name: str) -> str:
    if name.endswith("ies"):
        return name[:-3] + "y"
    return name.removesuffix("s")


def _looks_like_reference(column_name: str, target: EntitySnapshot) -> bool:
    stem = _stem(column_name)
    if not stem:
        return False
    target_name = target.name.lower()
    singular = _singularize(target_name)
    return stem in {target_name, singular} or singular.startswith(stem)


def _primary_key_of(entity: EntitySnapshot):
    return next((column for column in entity.columns if column.is_pk), None)


async def probe_relationships(
    adapter: SourceAdapter,
    snapshot: StructuralSnapshot,
    min_hit_rate: float = 0.9,
    sample_limit: int = 1000,
) -> list[CandidateRelationship]:
    declared = {
        (entity.identity, column)
        for entity in snapshot.entities
        for foreign_key in entity.foreign_keys
        for column in foreign_key.from_columns
    }
    tables = [entity for entity in snapshot.entities if entity.kind == "table"]
    results: list[CandidateRelationship] = []

    for source in tables:
        for column in source.columns:
            if column.is_pk or (source.identity, column.name) in declared:
                continue
            if not _is_integer(column.data_type):
                continue

            for target in tables:
                if target.identity == source.identity:
                    continue
                primary_key = _primary_key_of(target)
                if primary_key is None or not _is_integer(primary_key.data_type):
                    continue
                if not _looks_like_reference(column.name, target):
                    continue

                stats = await adapter.containment(
                    source, column.name, target, primary_key.name, limit=sample_limit
                )
                if stats.distinct_source_values == 0 or stats.hit_rate < min_hit_rate:
                    continue

                results.append(
                    CandidateRelationship(
                        from_identity=source.identity,
                        from_column=column.name,
                        to_identity=target.identity,
                        to_column=primary_key.name,
                        hit_rate=stats.hit_rate,
                        distinct_source_values=stats.distinct_source_values,
                        confidence=round(min(1.0, stats.hit_rate * 0.9 + 0.1), 3),
                    )
                )
    return results
