import pytest

from jamasp.adapters.postgres import PostgresAdapter
from jamasp.safety.readonly import UnsafeQueryError


@pytest.mark.asyncio
async def test_test_connection_reports_healthy(hr_dsn):
    report = await PostgresAdapter(hr_dsn).test_connection()
    assert report.healthy is True
    assert "PostgreSQL" in report.server_version


@pytest.mark.asyncio
async def test_introspect_finds_tables_and_views(hr_dsn):
    snapshot = await PostgresAdapter(hr_dsn).introspect()
    names = {entity.name: entity for entity in snapshot.entities}
    assert {"departments", "employees", "leave_requests", "t_mst_01"} <= names.keys()
    assert names["v_active_employees"].kind == "view"
    assert snapshot.dialect == "postgres"


@pytest.mark.asyncio
async def test_introspect_captures_columns_pk_fk_and_comments(hr_dsn):
    snapshot = await PostgresAdapter(hr_dsn).introspect()
    by_name = {entity.name: entity for entity in snapshot.entities}

    employees = by_name["employees"]
    assert [column.name for column in employees.columns][:3] == ["id", "full_name", "national_id"]
    assert next(c for c in employees.columns if c.name == "id").is_pk is True
    assert next(c for c in employees.columns if c.name == "full_name").nullable is False
    assert employees.foreign_keys[0].to_table == "departments"

    assert by_name["departments"].comment == "واحدهای سازمانی"
    status = next(c for c in by_name["leave_requests"].columns if c.name == "status")
    assert "در انتظار" in status.comment


@pytest.mark.asyncio
async def test_leave_requests_has_no_declared_foreign_key(hr_dsn):
    snapshot = await PostgresAdapter(hr_dsn).introspect()
    by_name = {entity.name: entity for entity in snapshot.entities}
    assert by_name["leave_requests"].foreign_keys == ()


@pytest.mark.asyncio
async def test_snapshot_hash_is_stable_across_runs(hr_dsn):
    first = await PostgresAdapter(hr_dsn).introspect()
    second = await PostgresAdapter(hr_dsn).introspect()
    entity = next(e for e in first.entities if e.name == "employees")
    other = next(e for e in second.entities if e.name == "employees")
    assert first.hash_for(entity) == second.hash_for(other)


@pytest.mark.asyncio
async def test_execute_readonly_rejects_writes(hr_dsn):
    with pytest.raises(UnsafeQueryError):
        await PostgresAdapter(hr_dsn).execute_readonly("DELETE FROM employees", limit=10)


@pytest.mark.asyncio
async def test_execute_readonly_enforces_row_limit(hr_dsn):
    rows = await PostgresAdapter(hr_dsn).execute_readonly("SELECT * FROM employees", limit=2)
    assert len(rows) == 2
