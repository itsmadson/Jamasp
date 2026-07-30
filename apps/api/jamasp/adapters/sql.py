"""What every SQL engine has in common, and the seams where they differ.

Reflection, sampling and bounded reads are the same shape everywhere — SQLAlchemy
reflects any dialect, and sqlglot rewrites a LIMIT into whatever the engine spells
it as. What actually differs is small and named here: how identifiers are quoted,
which schemas are the engine's own, how a statement timeout is set, and whether the
planner will hand over column statistics for free.

Subclasses override those seams. Nothing else should need overriding, and a new
engine that does need more is a signal the seam is in the wrong place.
"""

from typing import Any

from sqlalchemy import Connection, inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from jamasp.adapters.dsn import normalise_dsn
from jamasp.pipeline.snapshot import (
    ColumnInfo,
    ColumnStats,
    ContainmentStats,
    EntitySnapshot,
    ForeignKeyInfo,
    HealthReport,
    StructuralSnapshot,
)
from jamasp.safety.readonly import apply_limit, assert_readonly


class SqlAdapter:
    """Base for every SQL source. Not usable directly — pick a dialect."""

    # The name sqlglot and our safety layer know this engine by.
    dialect: str = ""
    # The SourceKind value, which is also the key into ENGINES.
    kind: str = ""
    # Schemas belonging to the engine rather than to the user's data.
    system_schemas: frozenset[str] = frozenset()
    version_sql: str = "SELECT version()"

    def __init__(self, dsn: str) -> None:
        self._engine = create_async_engine(
            normalise_dsn(dsn, self.kind), pool_pre_ping=True
        )

    # ------------------------------------------------------------------ seams

    def quote(self, identifier: str) -> str:
        """ANSI double quotes. MySQL and SQL Server disagree; they override."""
        return '"' + identifier.replace('"', '""') + '"'

    def qualify(self, entity: EntitySnapshot) -> str:
        return f"{self.quote(entity.schema_name)}.{self.quote(entity.name)}"

    def cast_text(self, expression: str) -> str:
        return f"CAST({expression} AS VARCHAR(4000))"

    def count_where(self, condition: str) -> str:
        """Conditional count.

        Postgres has FILTER, and it reads better, but SUM(CASE WHEN) is the form
        every engine accepts — including Postgres — so it is the default.
        """
        return f"SUM(CASE WHEN {condition} THEN 1 ELSE 0 END)"

    async def _apply_timeout(self, connection: Any, timeout_s: int) -> None:
        """Bound a single statement. No-op where the engine has no equivalent."""
        return

    async def _row_counts(self, connection: Any) -> dict[tuple[str, str], int]:
        """Approximate row counts, when the engine keeps them cheaply."""
        return {}

    # -------------------------------------------------------------- contract

    async def test_connection(self) -> HealthReport:
        try:
            async with self._engine.connect() as connection:
                version = (await connection.execute(text(self.version_sql))).scalar_one()
            return HealthReport(healthy=True, server_version=str(version))
        except Exception as exc:  # noqa: BLE001 - any driver error must reach the admin verbatim
            return HealthReport(healthy=False, error=str(exc))

    async def introspect(self) -> StructuralSnapshot:
        async with self._engine.connect() as connection:
            entities = await connection.run_sync(self._reflect)
            try:
                row_counts = await self._row_counts(connection)
            except Exception:  # noqa: BLE001 - an estimate is a nicety, not the scan
                row_counts = {}

        entities = tuple(
            EntitySnapshot(
                **{**entity.__dict__, "row_count_approx": row_counts.get(entity.identity)}
            )
            for entity in entities
        )
        return StructuralSnapshot(dialect=self.dialect, entities=entities)

    def _reflect(self, connection: Connection) -> tuple[EntitySnapshot, ...]:
        """Runs inside run_sync: SQLAlchemy reflection has no async API."""
        inspector = inspect(connection)
        entities: list[EntitySnapshot] = []

        for schema in self._schemas(inspector):
            named_kinds = [
                *((name, "table") for name in inspector.get_table_names(schema=schema)),
                *((name, "view") for name in inspector.get_view_names(schema=schema)),
            ]
            for name, kind in named_kinds:
                entities.append(self._reflect_one(inspector, schema, name, kind))

        # Sorted so two runs of the same schema produce byte-identical snapshots.
        return tuple(sorted(entities, key=lambda entity: entity.identity))

    def _schemas(self, inspector) -> list[str]:
        return [
            schema
            for schema in inspector.get_schema_names()
            if schema not in self.system_schemas
        ]

    def _reflect_one(self, inspector, schema: str, name: str, kind: str) -> EntitySnapshot:
        primary_key = set(
            (inspector.get_pk_constraint(name, schema=schema) or {}).get(
                "constrained_columns"
            )
            or []
        )
        columns = tuple(
            ColumnInfo(
                name=column["name"],
                data_type=str(column["type"]),
                nullable=bool(column["nullable"]),
                is_pk=column["name"] in primary_key,
                ordinal=ordinal,
                default=None if column.get("default") is None else str(column["default"]),
                comment=column.get("comment"),
            )
            for ordinal, column in enumerate(inspector.get_columns(name, schema=schema))
        )
        foreign_keys = tuple(
            ForeignKeyInfo(
                from_columns=tuple(fk["constrained_columns"]),
                to_schema=fk.get("referred_schema") or schema,
                to_table=fk["referred_table"],
                to_columns=tuple(fk["referred_columns"]),
            )
            for fk in inspector.get_foreign_keys(name, schema=schema)
        )
        unique_constraints = tuple(
            tuple(constraint["column_names"])
            for constraint in inspector.get_unique_constraints(name, schema=schema)
        )
        indexes = tuple(
            sorted(str(index["name"]) for index in inspector.get_indexes(name, schema=schema))
        )
        try:
            comment = (inspector.get_table_comment(name, schema=schema) or {}).get("text")
        except NotImplementedError:
            # Not every dialect reflects table comments; the table still describes.
            comment = None

        return EntitySnapshot(
            kind=kind,
            schema_name=schema,
            name=name,
            columns=columns,
            foreign_keys=foreign_keys,
            unique_constraints=unique_constraints,
            indexes=indexes,
            comment=comment,
        )

    async def execute_readonly(
        self, sql: str, limit: int = 1000, timeout_s: int = 30
    ) -> list[dict[str, Any]]:
        assert_readonly(sql, self.dialect)
        bounded = apply_limit(sql, self.dialect, limit)
        async with self._engine.connect() as connection, connection.begin():
            await self._apply_timeout(connection, timeout_s)
            result = await connection.execute(text(bounded))
            return [dict(row) for row in result.mappings()]

    async def table_stats(self, entity: EntitySnapshot) -> dict[str, ColumnStats]:
        """Free statistics from the planner, where the engine keeps them."""
        return {}

    async def column_stats(self, entity: EntitySnapshot, column: str) -> ColumnStats:
        target = self.qualify(entity)
        quoted = self.quote(column)
        sql = (
            f"SELECT count(DISTINCT {quoted}) AS distinct_count, "
            f"count(*) AS total, "
            f"{self.count_where(f'{quoted} IS NULL')} AS nulls, "
            f"min({self.cast_text(quoted)}) AS min_value, "
            f"max({self.cast_text(quoted)}) AS max_value "
            f"FROM {target}"
        )
        rows = await self.execute_readonly(sql, limit=1)
        if not rows:
            return ColumnStats()
        row = rows[0]
        total = row["total"] or 0
        return ColumnStats(
            distinct_count=int(row["distinct_count"]) if row["distinct_count"] is not None else None,
            # float(), because a conditional count comes back as Decimal on MySQL
            # and as int on Postgres, and the field is declared a float.
            null_ratio=(float(row["nulls"] or 0) / float(total)) if total else None,
            min_value=row["min_value"],
            max_value=row["max_value"],
        )

    async def distinct_values(
        self, entity: EntitySnapshot, column: str, limit: int
    ) -> list[Any]:
        target = self.qualify(entity)
        quoted = self.quote(column)
        sql = (
            f"SELECT DISTINCT {quoted} AS value FROM {target} "
            f"WHERE {quoted} IS NOT NULL ORDER BY 1"
        )
        rows = await self.execute_readonly(sql, limit=limit)
        return [row["value"] for row in rows]

    async def sample(
        self, entity: EntitySnapshot, columns: list[str], limit: int
    ) -> list[dict[str, Any]]:
        target = self.qualify(entity)
        projection = ", ".join(self.quote(column) for column in columns) or "*"
        return await self.execute_readonly(f"SELECT {projection} FROM {target}", limit=limit)

    async def containment(
        self,
        source: EntitySnapshot,
        source_column: str,
        target: EntitySnapshot,
        target_column: str,
        limit: int,
    ) -> ContainmentStats:
        source_table = self.qualify(source)
        target_table = self.qualify(target)
        source_quoted, target_quoted = self.quote(source_column), self.quote(target_column)
        matched = self.count_where(
            f"EXISTS (SELECT 1 FROM {target_table} t WHERE t.{target_quoted} = s.value)"
        )
        sql = (
            f"SELECT count(*) AS distinct_source_values, {matched} AS matched "
            f"FROM (SELECT DISTINCT {source_quoted} AS value FROM {source_table} "
            f"      WHERE {source_quoted} IS NOT NULL LIMIT {int(limit)}) s"
        )
        # sqlglot rewrites the inner LIMIT for engines that spell it differently.
        rows = await self.execute_readonly(sql, limit=1)
        if not rows:
            return ContainmentStats(hit_rate=0.0, distinct_source_values=0)
        total = rows[0]["distinct_source_values"] or 0
        matched_count = rows[0]["matched"] or 0
        return ContainmentStats(
            hit_rate=(matched_count / total) if total else 0.0,
            distinct_source_values=total,
        )
