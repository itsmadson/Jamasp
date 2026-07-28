import pytest
import pytest_asyncio

from agah.adapters.postgres import PostgresAdapter
from agah.models.entity import PIIClass
from agah.models.source import SamplingPolicy
from agah.pipeline.profile import profile_entity


@pytest_asyncio.fixture
async def employees_snapshot(hr_dsn):
    snapshot = await PostgresAdapter(hr_dsn).introspect()
    return next(entity for entity in snapshot.entities if entity.name == "employees")


@pytest.mark.asyncio
async def test_profile_collects_distinct_values_for_low_cardinality(hr_dsn):
    adapter = PostgresAdapter(hr_dsn)
    snapshot = await adapter.introspect()
    leave = next(entity for entity in snapshot.entities if entity.name == "leave_requests")

    profile = await profile_entity(adapter, leave, SamplingPolicy.MASKED)
    status = next(column for column in profile.columns if column.name == "status")
    assert sorted(status.sample_values) == [1, 2, 3]
    assert status.distinct_count == 3


@pytest.mark.asyncio
async def test_high_class_columns_have_no_sample_values(hr_dsn, employees_snapshot):
    profile = await profile_entity(
        PostgresAdapter(hr_dsn), employees_snapshot, SamplingPolicy.MASKED
    )
    national_id = next(column for column in profile.columns if column.name == "national_id")
    assert national_id.pii_class is PIIClass.HIGH
    assert national_id.sample_values == []


@pytest.mark.asyncio
async def test_no_raw_pii_anywhere_in_profile(hr_dsn, employees_snapshot):
    """The load-bearing privacy test: real PII must not survive profiling."""
    profile = await profile_entity(
        PostgresAdapter(hr_dsn), employees_snapshot, SamplingPolicy.MASKED
    )
    blob = repr(profile)
    for secret in ("0079542619", "0084575941", "09121234567", "09354445566", "120000000"):
        assert secret not in blob


@pytest.mark.asyncio
async def test_schema_only_policy_collects_no_values(hr_dsn, employees_snapshot):
    profile = await profile_entity(
        PostgresAdapter(hr_dsn), employees_snapshot, SamplingPolicy.SCHEMA_ONLY
    )
    assert profile.sample_rows == []
    assert all(column.sample_values == [] for column in profile.columns)
    assert all(column.null_ratio is not None for column in profile.columns)


@pytest.mark.asyncio
async def test_opaque_column_name_still_masked_by_value_shape(hr_dsn):
    adapter = PostgresAdapter(hr_dsn)
    snapshot = await adapter.introspect()
    legacy = next(entity for entity in snapshot.entities if entity.name == "t_mst_01")
    profile = await profile_entity(adapter, legacy, SamplingPolicy.MASKED)
    fld_003 = next(column for column in profile.columns if column.name == "fld_003")
    assert fld_003.pii_class is PIIClass.LOW
    assert all("***" in str(value) for value in fld_003.sample_values)
