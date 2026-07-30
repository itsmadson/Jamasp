"""The contract every data source implements.

SQL dialects and REST APIs both reduce to: describe your structure, let me
sample it safely, and let me run a bounded read-only query.
"""

from typing import Any, Protocol, runtime_checkable

from jamasp.pipeline.snapshot import (
    ColumnStats,
    ContainmentStats,
    EntitySnapshot,
    HealthReport,
    StructuralSnapshot,
)

__all__ = [
    "ColumnStats",
    "ContainmentStats",
    "EntitySnapshot",
    "HealthReport",
    "SourceAdapter",
    "StructuralSnapshot",
]


@runtime_checkable
class SourceAdapter(Protocol):
    dialect: str

    async def test_connection(self) -> HealthReport: ...

    async def introspect(self) -> StructuralSnapshot: ...

    async def column_stats(self, entity: EntitySnapshot, column: str) -> ColumnStats: ...

    async def distinct_values(
        self, entity: EntitySnapshot, column: str, limit: int
    ) -> list[Any]: ...

    async def sample(
        self, entity: EntitySnapshot, columns: list[str], limit: int
    ) -> list[dict[str, Any]]: ...

    async def containment(
        self,
        source: EntitySnapshot,
        source_column: str,
        target: EntitySnapshot,
        target_column: str,
        limit: int,
    ) -> ContainmentStats: ...

    async def execute_readonly(
        self, sql: str, limit: int = 1000, timeout_s: int = 30
    ) -> list[dict[str, Any]]: ...
