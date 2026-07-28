"""Deterministic structural types shared by every adapter.

A snapshot contains no AI output and no data values — only structure. It is the
diff basis for re-scans, so it must be byte-stable across runs of the same schema.
"""

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

Identity = tuple[str, str]


@dataclass(frozen=True)
class ColumnInfo:
    name: str
    data_type: str
    nullable: bool
    is_pk: bool
    ordinal: int
    default: str | None = None
    comment: str | None = None


@dataclass(frozen=True)
class ForeignKeyInfo:
    from_columns: tuple[str, ...]
    to_schema: str
    to_table: str
    to_columns: tuple[str, ...]


@dataclass(frozen=True)
class EntitySnapshot:
    kind: str
    schema_name: str
    name: str
    columns: tuple[ColumnInfo, ...]
    foreign_keys: tuple[ForeignKeyInfo, ...] = ()
    unique_constraints: tuple[tuple[str, ...], ...] = ()
    indexes: tuple[str, ...] = ()
    comment: str | None = None
    row_count_approx: int | None = None

    @property
    def identity(self) -> Identity:
        return (self.schema_name, self.name)


@dataclass(frozen=True)
class StructuralSnapshot:
    dialect: str
    entities: tuple[EntitySnapshot, ...]
    taken_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def by_identity(self) -> dict[Identity, EntitySnapshot]:
        return {entity.identity: entity for entity in self.entities}

    def hash_for(self, entity: EntitySnapshot) -> str:
        payload = asdict(entity)
        # Row counts drift constantly; including them would make every rescan
        # report every table as changed.
        payload.pop("row_count_approx", None)
        blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(blob.encode()).hexdigest()

    def to_json(self) -> dict[str, Any]:
        return {
            "dialect": self.dialect,
            "taken_at": self.taken_at.isoformat(),
            "entities": [asdict(entity) for entity in self.entities],
        }


@dataclass(frozen=True)
class HealthReport:
    healthy: bool
    server_version: str = ""
    error: str | None = None


@dataclass(frozen=True)
class ColumnStats:
    distinct_count: int | None = None
    null_ratio: float | None = None
    min_value: Any = None
    max_value: Any = None


@dataclass(frozen=True)
class ContainmentStats:
    hit_rate: float
    distinct_source_values: int
