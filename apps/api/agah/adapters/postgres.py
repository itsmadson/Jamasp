from typing import Any

from sqlalchemy import Connection, inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from agah.pipeline.snapshot import (
    ColumnInfo,
    ColumnStats,
    ContainmentStats,
    EntitySnapshot,
    ForeignKeyInfo,
    HealthReport,
    StructuralSnapshot,
)
from agah.safety.readonly import apply_limit, assert_readonly

SYSTEM_SCHEMAS = {"pg_catalog", "information_schema", "pg_toast"}

ROW_COUNTS_SQL = text("SELECT schemaname, relname, n_live_tup FROM pg_stat_user_tables")


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


class PostgresAdapter:
    dialect = "postgres"

    def __init__(self, dsn: str) -> None:
        self._engine = create_async_engine(dsn, pool_pre_ping=True)

    async def test_connection(self) -> HealthReport:
        try:
            async with self._engine.connect() as connection:
                version = (await connection.execute(text("SELECT version()"))).scalar_one()
            return HealthReport(healthy=True, server_version=str(version))
        except Exception as exc:  # noqa: BLE001 - any driver error must reach the admin verbatim
            return HealthReport(healthy=False, error=str(exc))

    async def introspect(self) -> StructuralSnapshot:
        async with self._engine.connect() as connection:
            entities = await connection.run_sync(self._reflect)
            row_counts = {
                (row.schemaname, row.relname): row.n_live_tup
                for row in (await connection.execute(ROW_COUNTS_SQL))
            }

        entities = tuple(
            EntitySnapshot(**{**entity.__dict__,
                              "row_count_approx": row_counts.get(entity.identity)})
            for entity in entities
        )
        return StructuralSnapshot(dialect=self.dialect, entities=entities)

    def _reflect(self, connection: Connection) -> tuple[EntitySnapshot, ...]:
        """Runs inside run_sync: SQLAlchemy reflection has no async API."""
        inspector = inspect(connection)
        entities: list[EntitySnapshot] = []

        for schema in inspector.get_schema_names():
            if schema in SYSTEM_SCHEMAS:
                continue
            named_kinds = [
                *((name, "table") for name in inspector.get_table_names(schema=schema)),
                *((name, "view") for name in inspector.get_view_names(schema=schema)),
            ]
            for name, kind in named_kinds:
                entities.append(self._reflect_one(inspector, schema, name, kind))

        # Sorted so two runs of the same schema produce byte-identical snapshots.
        return tuple(sorted(entities, key=lambda entity: entity.identity))

    def _reflect_one(self, inspector, schema: str, name: str, kind: str) -> EntitySnapshot:
        primary_key = set(
            (inspector.get_pk_constraint(name, schema=schema) or {}).get(
                "constrained_columns"
            ) or []
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
            sorted(index["name"] for index in inspector.get_indexes(name, schema=schema))
        )
        comment = (inspector.get_table_comment(name, schema=schema) or {}).get("text")

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
        async with self._engine.connect() as connection:
            await connection.execute(text(f"SET LOCAL statement_timeout = {timeout_s * 1000}"))
            result = await connection.execute(text(bounded))
            return [dict(row) for row in result.mappings()]

    async def column_stats(self, entity: EntitySnapshot, column: str) -> ColumnStats:
        target = f"{_quote(entity.schema_name)}.{_quote(entity.name)}"
        quoted = _quote(column)
        sql = (
            f"SELECT count(DISTINCT {quoted}) AS distinct_count, "
            f"count(*) AS total, "
            f"count(*) FILTER (WHERE {quoted} IS NULL) AS nulls, "
            f"min({quoted}::text) AS min_value, max({quoted}::text) AS max_value "
            f"FROM {target}"
        )
        rows = await self.execute_readonly(sql, limit=1)
        if not rows:
            return ColumnStats()
        row = rows[0]
        total = row["total"] or 0
        return ColumnStats(
            distinct_count=row["distinct_count"],
            null_ratio=(row["nulls"] / total) if total else None,
            min_value=row["min_value"],
            max_value=row["max_value"],
        )

    async def distinct_values(
        self, entity: EntitySnapshot, column: str, limit: int
    ) -> list[Any]:
        target = f"{_quote(entity.schema_name)}.{_quote(entity.name)}"
        quoted = _quote(column)
        sql = (
            f"SELECT DISTINCT {quoted} AS value FROM {target} "
            f"WHERE {quoted} IS NOT NULL ORDER BY 1"
        )
        rows = await self.execute_readonly(sql, limit=limit)
        return [row["value"] for row in rows]

    async def sample(
        self, entity: EntitySnapshot, columns: list[str], limit: int
    ) -> list[dict[str, Any]]:
        target = f"{_quote(entity.schema_name)}.{_quote(entity.name)}"
        projection = ", ".join(_quote(column) for column in columns) or "*"
        return await self.execute_readonly(f"SELECT {projection} FROM {target}", limit=limit)

    async def containment(
        self,
        source: EntitySnapshot,
        source_column: str,
        target: EntitySnapshot,
        target_column: str,
        limit: int,
    ) -> ContainmentStats:
        source_table = f"{_quote(source.schema_name)}.{_quote(source.name)}"
        target_table = f"{_quote(target.schema_name)}.{_quote(target.name)}"
        source_quoted, target_quoted = _quote(source_column), _quote(target_column)
        sql = (
            f"SELECT count(*) AS distinct_source_values, "
            f"count(*) FILTER (WHERE EXISTS ("
            f"  SELECT 1 FROM {target_table} t WHERE t.{target_quoted} = s.value"
            f")) AS matched "
            f"FROM (SELECT DISTINCT {source_quoted} AS value FROM {source_table} "
            f"      WHERE {source_quoted} IS NOT NULL LIMIT {int(limit)}) s"
        )
        rows = await self.execute_readonly(sql, limit=1)
        if not rows:
            return ContainmentStats(hit_rate=0.0, distinct_source_values=0)
        total = rows[0]["distinct_source_values"] or 0
        matched = rows[0]["matched"] or 0
        return ContainmentStats(
            hit_rate=(matched / total) if total else 0.0,
            distinct_source_values=total,
        )
