"""PostgreSQL.

Everything portable lives in SqlAdapter. What is left here is the one thing
Postgres does that the others do not: hand over per-column statistics the planner
has already computed, for free.
"""

from typing import Any

from sqlalchemy import text

from jamasp.adapters.sql import SqlAdapter
from jamasp.pipeline.snapshot import ColumnStats, EntitySnapshot

SYSTEM_SCHEMAS = frozenset({"pg_catalog", "information_schema", "pg_toast"})

ROW_COUNTS_SQL = text("SELECT schemaname, relname, n_live_tup FROM pg_stat_user_tables")

# The planner already keeps distinct counts and null fractions for every analyzed
# column. Reading them is one round trip per table and zero table scans; computing
# them with COUNT(DISTINCT ...) is one full scan per column, which over a WAN link
# is the difference between seconds and half an hour.
TABLE_STATS_SQL = text("""
    SELECT attname, n_distinct, null_frac, most_common_vals::text::text[] AS common_values
    FROM pg_stats
    WHERE schemaname = :schema AND tablename = :table
""")


class PostgresAdapter(SqlAdapter):
    dialect = "postgres"
    kind = "postgres"
    system_schemas = SYSTEM_SCHEMAS
    version_sql = "SELECT version()"

    def count_where(self, condition: str) -> str:
        # FILTER is the clearer spelling, and Postgres is the engine that has it.
        return f"count(*) FILTER (WHERE {condition})"

    def cast_text(self, expression: str) -> str:
        return f"{expression}::text"

    async def _apply_timeout(self, connection: Any, timeout_s: int) -> None:
        # Callers run this inside an explicit transaction, so SET LOCAL binds.
        # Without one it silently applies to nothing and a slow query can hang the
        # whole scan indefinitely.
        await connection.execute(text(f"SET LOCAL statement_timeout = {int(timeout_s) * 1000}"))

    async def _row_counts(self, connection: Any) -> dict[tuple[str, str], int]:
        result = await connection.execute(ROW_COUNTS_SQL)
        return {(row.schemaname, row.relname): row.n_live_tup for row in result}

    async def table_stats(self, entity: EntitySnapshot) -> dict[str, ColumnStats]:
        """Whole-table statistics in one round trip, from the planner's own numbers.

        n_distinct is negative when Postgres stores it as a fraction of the row
        count, which is why it is scaled back here rather than used raw.
        """
        rows_estimate = entity.row_count_approx or 0
        try:
            async with self._engine.connect() as connection:
                result = await connection.execute(
                    TABLE_STATS_SQL,
                    {"schema": entity.schema_name, "table": entity.name},
                )
                records = result.mappings().all()
        except Exception:  # noqa: BLE001 - fall back to per-column queries
            return {}

        stats: dict[str, ColumnStats] = {}
        for record in records:
            raw = record["n_distinct"]
            if raw is None:
                distinct = None
            elif raw < 0:
                distinct = int(abs(raw) * rows_estimate) if rows_estimate else None
            else:
                distinct = int(raw)
            stats[record["attname"]] = ColumnStats(
                distinct_count=distinct,
                null_ratio=float(record["null_frac"]) if record["null_frac"] is not None else None,
                common_values=tuple(record["common_values"] or ()),
            )
        return stats
