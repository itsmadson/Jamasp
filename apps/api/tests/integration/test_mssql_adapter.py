"""SQL Server against a real SQL Server.

Skipped unless an ODBC driver is installed locally — the API image has one, but a
developer machine may not, and a skipped test is honest where a mocked one would
not be. The container is large, so this file is the only place that pays for it.
"""

from collections.abc import Iterator

import pytest
import pytest_asyncio
from sqlalchemy import create_engine, text

pyodbc = pytest.importorskip("pyodbc", reason="needs unixODBC and an ODBC driver")

from jamasp.adapters.mssql import MssqlAdapter
from jamasp.models.source import SamplingPolicy
from jamasp.pipeline.profile import profile_entity
from jamasp.safety.readonly import UnsafeQueryError

DRIVER = "ODBC Driver 18 for SQL Server"

pytestmark = pytest.mark.skipif(
    DRIVER not in pyodbc.drivers(),
    reason=f"'{DRIVER}' is not installed on this machine",
)

SCHEMA = [
    "CREATE SCHEMA hr",
    """CREATE TABLE hr.departments (
        id INT PRIMARY KEY,
        name NVARCHAR(80) NOT NULL
    )""",
    """CREATE TABLE hr.employees (
        id INT PRIMARY KEY,
        dept_id INT,
        full_name NVARCHAR(120) NOT NULL,
        email NVARCHAR(160),
        salary DECIMAL(10, 2),
        CONSTRAINT fk_dept FOREIGN KEY (dept_id) REFERENCES hr.departments (id)
    )""",
    # "order" is reserved; only bracket quoting reaches it.
    """CREATE TABLE hr.[order] (
        id INT PRIMARY KEY,
        [select] NVARCHAR(40)
    )""",
    "CREATE VIEW hr.active_employees AS SELECT id, full_name FROM hr.employees",
]

ROWS = [
    "INSERT INTO hr.departments (id, name) VALUES (1, N'Engineering'), (2, N'Sales')",
    """INSERT INTO hr.employees (id, dept_id, full_name, email, salary) VALUES
        (1, 1, N'Ali Rezaei', N'ali@example.com', 5000.00),
        (2, 1, N'Sara Ahmadi', N'sara@example.com', 6200.50),
        (3, 2, N'Reza Karimi', NULL, 4100.00)""",
    "INSERT INTO hr.[order] (id, [select]) VALUES (1, N'reserved words')",
]


@pytest.fixture(scope="session")
def mssql_dsn() -> Iterator[str]:
    from testcontainers.mssql import SqlServerContainer

    with SqlServerContainer("mcr.microsoft.com/mssql/server:2022-latest") as container:
        url = container.get_connection_url()
        sync_url = (
            url.replace("mssql+pymssql://", "mssql+pyodbc://", 1)
            + f"?driver={DRIVER.replace(' ', '+')}&TrustServerCertificate=yes"
        )
        engine = create_engine(sync_url)
        with engine.connect() as connection:
            for statement in [*SCHEMA, *ROWS]:
                connection.execute(text(statement))
                connection.commit()
        engine.dispose()
        yield url


@pytest_asyncio.fixture
async def adapter(mssql_dsn: str) -> MssqlAdapter:
    return MssqlAdapter(mssql_dsn)


@pytest.mark.asyncio
async def test_connects_and_reports_its_version(adapter):
    health = await adapter.test_connection()
    assert health.healthy
    assert "SQL Server" in (health.server_version or "")


@pytest.mark.asyncio
async def test_reflects_a_user_schema_and_skips_the_servers_own(adapter):
    snapshot = await adapter.introspect()

    by_name = {entity.name: entity for entity in snapshot.entities}
    assert {"departments", "employees", "order", "active_employees"} <= set(by_name)
    assert by_name["employees"].schema_name == "hr"

    schemas = {entity.schema_name for entity in snapshot.entities}
    assert "sys" not in schemas
    assert "INFORMATION_SCHEMA" not in schemas

    employees = by_name["employees"]
    assert [column.name for column in employees.columns if column.is_pk] == ["id"]
    assert employees.foreign_keys[0].to_table == "departments"
    assert by_name["active_employees"].kind == "view"


@pytest.mark.asyncio
async def test_samples_a_table_named_with_a_reserved_word(adapter):
    """Bracket quoting, not double quotes — SQL Server rejects the ANSI form by
    default unless QUOTED_IDENTIFIER is on."""
    snapshot = await adapter.introspect()
    entity = next(e for e in snapshot.entities if e.name == "order")

    rows = await adapter.sample(entity, ["id", "select"], limit=5)

    assert rows == [{"id": 1, "select": "reserved words"}]


@pytest.mark.asyncio
async def test_a_read_is_bounded_into_top_not_limit(adapter):
    """T-SQL has no LIMIT; sqlglot must rewrite the bound into TOP."""
    rows = await adapter.execute_readonly("SELECT id FROM hr.employees", limit=2)
    assert len(rows) == 2

    # The specific error, so this cannot pass because of an unrelated failure.
    with pytest.raises(UnsafeQueryError):
        await adapter.execute_readonly("DELETE FROM hr.employees")


@pytest.mark.asyncio
async def test_column_stats_come_back_as_plain_numbers(adapter):
    snapshot = await adapter.introspect()
    entity = next(e for e in snapshot.entities if e.name == "employees")

    stats = await adapter.column_stats(entity, "email")

    assert stats.distinct_count == 2
    assert isinstance(stats.null_ratio, float)
    assert stats.null_ratio == pytest.approx(1 / 3)


@pytest.mark.asyncio
async def test_row_count_estimates_come_from_the_engines_bookkeeping(adapter):
    snapshot = await adapter.introspect()
    employees = next(e for e in snapshot.entities if e.name == "employees")
    assert employees.row_count_approx == 3


@pytest.mark.asyncio
async def test_profiling_works_against_sql_server(adapter):
    snapshot = await adapter.introspect()
    entity = next(e for e in snapshot.entities if e.name == "employees")

    profile = await profile_entity(adapter, entity, SamplingPolicy.MASKED)

    by_name = {column.name: column for column in profile.columns}
    assert set(by_name) == {"id", "dept_id", "full_name", "email", "salary"}
    # Same masking policy as every other engine.
    assert all("***@" in str(value) for value in by_name["email"].sample_values)
