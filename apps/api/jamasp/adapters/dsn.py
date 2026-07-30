"""Accept the connection strings people actually have.

An admin pastes whatever their other tooling gave them — a JDBC URL, a plain
`postgresql://`, a psycopg2 URL, a `mysql://` from a config file. Only the async
driver form works with an async engine, so the difference is normalised here rather
than being the admin's problem.
"""

from dataclasses import dataclass


class InvalidDsnError(ValueError):
    pass


@dataclass(frozen=True)
class Engine:
    """How one database engine's connection strings are spelled."""

    kind: str
    label: str
    async_scheme: str
    # Everything an admin might paste that means this engine.
    accepted: tuple[str, ...]
    example: str


ENGINES: dict[str, Engine] = {
    "postgres": Engine(
        kind="postgres",
        label="PostgreSQL",
        async_scheme="postgresql+asyncpg://",
        accepted=(
            "postgresql+asyncpg://",
            "postgresql+psycopg2://",
            "postgresql+psycopg://",
            "postgresql://",
            "postgres://",
        ),
        example="postgresql://user:password@host:5432/database",
    ),
    "mysql": Engine(
        kind="mysql",
        label="MySQL or MariaDB",
        async_scheme="mysql+asyncmy://",
        accepted=(
            "mysql+asyncmy://",
            "mysql+aiomysql://",
            "mysql+pymysql://",
            "mysql+mysqldb://",
            "mysql://",
            "mariadb://",
        ),
        example="mysql://user:password@host:3306/database",
    ),
    "mssql": Engine(
        kind="mssql",
        label="SQL Server",
        async_scheme="mssql+aioodbc://",
        accepted=(
            "mssql+aioodbc://",
            "mssql+pyodbc://",
            "mssql+pymssql://",
            "mssql://",
            "sqlserver://",
        ),
        example="mssql://user:password@host:1433/database",
    ),
}


def normalise_dsn(dsn: str, kind: str) -> str:
    """Rewrite a connection string to the async driver form for its engine."""
    engine = ENGINES.get(kind)
    if engine is None:
        raise InvalidDsnError(f"unsupported source kind '{kind}'")

    value = (dsn or "").strip()
    if not value:
        raise InvalidDsnError("connection string is empty")

    if value.startswith("jdbc:"):
        raise InvalidDsnError(
            f"that is a jdbc url. Use {engine.example} "
            f"— the credentials are not part of a jdbc string"
        )

    if value.startswith(engine.async_scheme):
        return _finish(engine, value[len(engine.async_scheme) :])

    for prefix in engine.accepted:
        if value.startswith(prefix):
            # Only the scheme is replaced: everything after it, including a
            # percent-encoded password, is left exactly as given.
            return _finish(engine, value[len(prefix) :])

    scheme = value.split("://", 1)[0] if "://" in value else value[:20]
    raise InvalidDsnError(
        f"unsupported connection string for a {engine.label} source: '{scheme}'. "
        f"Expected {engine.example}"
    )


def _finish(engine: Engine, rest: str) -> str:
    dsn = engine.async_scheme + rest
    if engine.kind == "mssql" and "driver=" not in rest.lower():
        # pyodbc cannot connect without being told which installed driver to use,
        # and the error it raises otherwise names no cause an admin can act on.
        separator = "&" if "?" in rest else "?"
        dsn = f"{dsn}{separator}driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"
    return dsn


def normalise_postgres_dsn(dsn: str) -> str:
    """Kept for callers that predate multi-engine support."""
    return normalise_dsn(dsn, "postgres")
