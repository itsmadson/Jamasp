"""MySQL and MariaDB.

Two real differences from the base. Identifiers are backquoted, not double-quoted,
unless the server runs in ANSI_QUOTES mode — and assuming the mode is set is how a
scan fails on a perfectly ordinary server. And a MySQL "schema" is a database: the
connection already names one, so reflection must not wander into the others.
"""

import logging
from typing import Any

from sqlalchemy import text

from jamasp.adapters.sql import SqlAdapter
from jamasp.pipeline.snapshot import EntitySnapshot

logger = logging.getLogger(__name__)

SYSTEM_SCHEMAS = frozenset({"information_schema", "mysql", "performance_schema", "sys"})

# information_schema keeps an estimate that costs nothing to read. It is an
# estimate — InnoDB derives it from sampled pages — which is all the profiler wants.
ROW_COUNTS_SQL = text("""
    SELECT table_schema, table_name, table_rows
    FROM information_schema.tables
    WHERE table_schema NOT IN ('information_schema', 'mysql', 'performance_schema', 'sys')
""")


class MySQLAdapter(SqlAdapter):
    dialect = "mysql"
    kind = "mysql"
    system_schemas = SYSTEM_SCHEMAS
    version_sql = "SELECT VERSION()"

    def quote(self, identifier: str) -> str:
        return "`" + identifier.replace("`", "``") + "`"

    def cast_text(self, expression: str) -> str:
        # MySQL rejects CAST(... AS VARCHAR); CHAR is the spelling it accepts.
        return f"CAST({expression} AS CHAR)"

    async def _apply_timeout(self, connection: Any, timeout_s: int) -> None:
        # Milliseconds, and per-session rather than per-statement. MariaDB spells
        # it differently and does not have this variable at all, so a failure here
        # must not take the query with it.
        try:
            await connection.execute(
                text(f"SET SESSION MAX_EXECUTION_TIME = {int(timeout_s) * 1000}")
            )
        except Exception as exc:  # noqa: BLE001 - MariaDB, or a server that forbids SET
            # Worth a line: a bound that silently did not apply is how a slow
            # query hangs a scan with nothing in the log to explain it.
            logger.warning("could not set a statement timeout on MySQL: %s", exc)

    async def _row_counts(self, connection: Any) -> dict[tuple[str, str], int]:
        result = await connection.execute(ROW_COUNTS_SQL)
        return {
            (row.table_schema, row.table_name): row.table_rows
            for row in result
            if row.table_rows is not None
        }

    async def table_stats(self, entity: EntitySnapshot) -> dict[str, Any]:
        """MySQL keeps no per-column statistics a client can read cheaply.

        Returning nothing is correct rather than a gap: the profiler samples one
        page of rows per table and derives what it needs from those.
        """
        return {}
