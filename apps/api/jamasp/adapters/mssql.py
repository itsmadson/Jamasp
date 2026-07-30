"""Microsoft SQL Server.

Identifiers are bracketed. There is no per-session statement timeout the server
enforces — SET LOCK_TIMEOUT only covers waiting on locks — so the bound is set on
the driver instead, which is the only place it actually holds.
"""

import logging
from typing import Any

from sqlalchemy import text

from jamasp.adapters.sql import SqlAdapter

logger = logging.getLogger(__name__)

SYSTEM_SCHEMAS = frozenset({"sys", "INFORMATION_SCHEMA", "guest", "db_owner",
                            "db_accessadmin", "db_securityadmin", "db_ddladmin",
                            "db_backupoperator", "db_datareader", "db_datawriter",
                            "db_denydatareader", "db_denydatawriter"})

# sys.dm_db_partition_stats is maintained by the engine, so this is a read of
# bookkeeping rather than a count of rows.
ROW_COUNTS_SQL = text("""
    SELECT s.name AS schema_name, t.name AS table_name, SUM(p.row_count) AS row_count
    FROM sys.dm_db_partition_stats p
    JOIN sys.tables t ON t.object_id = p.object_id
    JOIN sys.schemas s ON s.schema_id = t.schema_id
    WHERE p.index_id IN (0, 1)
    GROUP BY s.name, t.name
""")


class MssqlAdapter(SqlAdapter):
    # sqlglot and our safety layer know SQL Server as "tsql".
    dialect = "tsql"
    kind = "mssql"
    system_schemas = SYSTEM_SCHEMAS
    version_sql = "SELECT @@VERSION"

    def quote(self, identifier: str) -> str:
        return "[" + identifier.replace("]", "]]") + "]"

    def cast_text(self, expression: str) -> str:
        return f"CAST({expression} AS NVARCHAR(4000))"

    async def _apply_timeout(self, connection: Any, timeout_s: int) -> None:
        """Bound the read at the driver.

        SET LOCK_TIMEOUT only bounds waiting for a lock, not a query that is busy
        scanning, so setting it would look like a timeout without being one. pyodbc
        exposes the real thing.
        """
        try:
            raw = await connection.get_raw_connection()
            raw.driver_connection.timeout = int(timeout_s)
        except Exception as exc:  # noqa: BLE001 - an unbounded read still beats no read
            logger.warning("could not set a query timeout on SQL Server: %s", exc)

    async def _row_counts(self, connection: Any) -> dict[tuple[str, str], int]:
        result = await connection.execute(ROW_COUNTS_SQL)
        return {
            (row.schema_name, row.table_name): row.row_count
            for row in result
            if row.row_count is not None
        }
