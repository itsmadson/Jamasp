from typing import Any

from jamasp.adapters.base import SourceAdapter
from jamasp.adapters.mssql import MssqlAdapter
from jamasp.adapters.mysql import MySQLAdapter
from jamasp.adapters.postgres import PostgresAdapter
from jamasp.models.source import SourceKind

SQL_ADAPTERS = {
    SourceKind.POSTGRES: PostgresAdapter,
    SourceKind.MYSQL: MySQLAdapter,
    SourceKind.MSSQL: MssqlAdapter,
}


def adapter_for(kind: SourceKind, config: dict[str, Any]) -> SourceAdapter:
    adapter = SQL_ADAPTERS.get(kind)
    if adapter is not None:
        return adapter(config["dsn"])
    raise NotImplementedError(
        f"no adapter for source kind '{kind}' yet; implement it against the "
        f"SourceAdapter protocol in jamasp/adapters/base.py"
    )
