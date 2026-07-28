import pytest
from sqlalchemy import select

from agah.models.entity import Entity, EntityStatus
from agah.models.source import DataSource, SamplingPolicy, SourceKind


@pytest.mark.asyncio
async def test_entity_defaults_to_pending_and_cascades(session):
    source = DataSource(
        name="HR",
        kind=SourceKind.POSTGRES,
        config_encrypted=b"x",
        sampling_policy=SamplingPolicy.MASKED,
    )
    session.add(source)
    await session.flush()

    entity = Entity(
        data_source_id=source.id,
        kind="table",
        schema_name="public",
        name="leave_requests",
        structural={"columns": []},
        structural_hash="abc",
    )
    session.add(entity)
    await session.flush()

    assert entity.status is EntityStatus.PENDING
    assert entity.version == 1

    await session.delete(source)
    await session.flush()
    remaining = await session.scalars(select(Entity))
    assert remaining.all() == []
