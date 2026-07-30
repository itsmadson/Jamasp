import pytest

from jamasp.adapters.postgres import PostgresAdapter
from jamasp.pipeline.probe import probe_relationships


@pytest.mark.asyncio
async def test_finds_undeclared_relationship(hr_dsn):
    adapter = PostgresAdapter(hr_dsn)
    found = await probe_relationships(adapter, await adapter.introspect())

    match = next(
        (
            candidate
            for candidate in found
            if candidate.from_identity[1] == "leave_requests"
            and candidate.from_column == "emp_id"
        ),
        None,
    )
    assert match is not None, "join probe missed leave_requests.emp_id -> employees.id"
    assert match.to_identity[1] == "employees"
    assert match.to_column == "id"
    assert match.hit_rate == 1.0


@pytest.mark.asyncio
async def test_does_not_report_already_declared_relationships(hr_dsn):
    adapter = PostgresAdapter(hr_dsn)
    found = await probe_relationships(adapter, await adapter.introspect())
    assert not any(
        candidate.from_column == "dept_id" and candidate.from_identity[1] == "employees"
        for candidate in found
    )


@pytest.mark.asyncio
async def test_rejects_candidates_below_hit_rate_threshold(hr_dsn):
    adapter = PostgresAdapter(hr_dsn)
    found = await probe_relationships(adapter, await adapter.introspect(), min_hit_rate=0.99)
    assert all(candidate.hit_rate >= 0.99 for candidate in found)


@pytest.mark.asyncio
async def test_ignores_type_mismatched_candidates(hr_dsn):
    adapter = PostgresAdapter(hr_dsn)
    found = await probe_relationships(adapter, await adapter.introspect())
    assert not any(candidate.from_column == "mobile" for candidate in found)
