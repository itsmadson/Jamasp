"""MySQL against a real MySQL server.

The point of these is that "it type-checks" proves nothing about a database
adapter. Backquoted identifiers, CAST(... AS CHAR), and a schema that means a
database rather than a namespace are all things that only fail when a real server
answers.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import create_engine, text
from testcontainers.mysql import MySqlContainer

from jamasp.adapters.mysql import MySQLAdapter
from jamasp.models.entity import PIIClass
from jamasp.models.source import SamplingPolicy
from jamasp.pipeline.profile import profile_entity
from jamasp.safety.readonly import UnsafeQueryError

SCHEMA = """
CREATE TABLE departments (
    id INT PRIMARY KEY,
    name VARCHAR(80) NOT NULL
);

CREATE TABLE employees (
    id INT PRIMARY KEY,
    dept_id INT,
    full_name VARCHAR(120) NOT NULL,
    email VARCHAR(160),
    salary DECIMAL(10, 2),
    CONSTRAINT fk_dept FOREIGN KEY (dept_id) REFERENCES departments (id)
);

CREATE TABLE `order` (
    id INT PRIMARY KEY,
    `select` VARCHAR(40)
);

CREATE VIEW active_employees AS SELECT id, full_name FROM employees;
"""

ROWS = """
INSERT INTO departments (id, name) VALUES (1, 'Engineering'), (2, 'Sales');
INSERT INTO employees (id, dept_id, full_name, email, salary) VALUES
    (1, 1, 'Ali Rezaei', 'ali@example.com', 5000.00),
    (2, 1, 'Sara Ahmadi', 'sara@example.com', 6200.50),
    (3, 2, 'Reza Karimi', NULL, 4100.00);
INSERT INTO `order` (id, `select`) VALUES (1, 'reserved words');
"""


@pytest.fixture(scope="session")
def mysql_dsn() -> Iterator[str]:
    with MySqlContainer("mysql:8.0") as container:
        url = container.get_connection_url()
        # Seeding runs synchronously, so it needs a sync driver; the adapter under
        # test does its own async normalisation of this same URL.
        engine = create_engine(url.replace("mysql://", "mysql+pymysql://", 1))
        with engine.begin() as connection:
            for statement in SCHEMA.split(";"):
                if statement.strip():
                    connection.execute(text(statement))
            for statement in ROWS.split(";"):
                if statement.strip():
                    connection.execute(text(statement))
        engine.dispose()
        yield url


@pytest_asyncio.fixture
async def adapter(mysql_dsn: str) -> MySQLAdapter:
    return MySQLAdapter(mysql_dsn)


@pytest.mark.asyncio
async def test_connects_and_reports_its_version(adapter):
    health = await adapter.test_connection()
    assert health.healthy
    assert health.server_version


@pytest.mark.asyncio
async def test_reflects_tables_views_and_keys(adapter):
    snapshot = await adapter.introspect()

    names = {entity.name for entity in snapshot.entities}
    assert {"departments", "employees", "order", "active_employees"} <= names

    employees = next(e for e in snapshot.entities if e.name == "employees")
    assert employees.kind == "table"
    assert {column.name for column in employees.columns} == {
        "id", "dept_id", "full_name", "email", "salary",
    }
    assert [column.name for column in employees.columns if column.is_pk] == ["id"]

    # The declared foreign key is what makes joins free — no probing needed.
    assert employees.foreign_keys
    assert employees.foreign_keys[0].to_table == "departments"

    view = next(e for e in snapshot.entities if e.name == "active_employees")
    assert view.kind == "view"


@pytest.mark.asyncio
async def test_does_not_wander_into_the_servers_own_databases(adapter):
    snapshot = await adapter.introspect()
    schemas = {entity.schema_name for entity in snapshot.entities}
    assert not schemas & {"mysql", "performance_schema", "sys", "information_schema"}


@pytest.mark.asyncio
async def test_samples_a_table_with_reserved_words_for_names(adapter):
    """`order` and `select` are keywords; only correct quoting reaches the rows."""
    snapshot = await adapter.introspect()
    entity = next(e for e in snapshot.entities if e.name == "order")

    rows = await adapter.sample(entity, ["id", "select"], limit=5)

    assert rows == [{"id": 1, "select": "reserved words"}]


@pytest.mark.asyncio
async def test_column_stats_use_a_cast_mysql_accepts(adapter):
    """CAST(x AS VARCHAR) is a syntax error on MySQL; CHAR is the accepted spelling."""
    snapshot = await adapter.introspect()
    entity = next(e for e in snapshot.entities if e.name == "employees")

    stats = await adapter.column_stats(entity, "email")

    assert stats.distinct_count == 2
    # One of three rows has no email. A conditional count is Decimal on MySQL, so
    # this also pins that the ratio is a real float rather than a Decimal that
    # merely prints like one.
    assert isinstance(stats.null_ratio, float)
    assert stats.null_ratio == pytest.approx(1 / 3)


@pytest.mark.asyncio
async def test_a_read_is_bounded_and_a_write_is_refused(adapter):
    rows = await adapter.execute_readonly("SELECT id FROM employees", limit=2)
    assert len(rows) == 2

    # The specific error, so this cannot pass because of an unrelated failure.
    with pytest.raises(UnsafeQueryError):
        await adapter.execute_readonly("DELETE FROM employees")


@pytest.mark.asyncio
async def test_profiling_a_mysql_table_produces_masked_samples(adapter):
    """The profiler is dialect-agnostic; this proves it against a second engine."""
    snapshot = await adapter.introspect()
    entity = next(e for e in snapshot.entities if e.name == "employees")

    profile = await profile_entity(adapter, entity, SamplingPolicy.MASKED)

    by_name = {column.name: column for column in profile.columns}
    assert by_name["full_name"].sample_values or by_name["id"].sample_values

    # Email is LOW, not HIGH: it is masked and kept rather than withheld, because
    # the shape of an address helps the model describe the column. The masking
    # must behave identically to Postgres — same policy, different engine.
    assert by_name["email"].pii_class is PIIClass.LOW
    assert all("***@" in str(value) for value in by_name["email"].sample_values)
    assert all("@example.com" in str(value) for value in by_name["email"].sample_values)


@pytest.mark.asyncio
async def test_containment_runs_without_postgres_only_syntax(adapter):
    """FILTER (WHERE ...) is Postgres-only; the base class uses SUM(CASE WHEN)."""
    snapshot = await adapter.introspect()
    employees = next(e for e in snapshot.entities if e.name == "employees")
    departments = next(e for e in snapshot.entities if e.name == "departments")

    stats = await adapter.containment(employees, "dept_id", departments, "id", limit=100)

    # Every dept_id exists in departments.
    assert stats.hit_rate == 1.0
    assert stats.distinct_source_values == 2


def test_the_hr_fixture_schema_file_is_postgres_only():
    """Documents why this file defines its own schema instead of reusing it."""
    fixture = Path(__file__).parent.parent / "fixtures" / "hr_schema.sql"
    assert fixture.exists()
    text_content = fixture.read_text()
    assert "SERIAL" in text_content or "serial" in text_content
