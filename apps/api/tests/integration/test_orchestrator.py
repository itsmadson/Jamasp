import json
from dataclasses import replace
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select

from agah.llm.base import Completion
from agah.models.entity import Entity, EntityStatus, Field, PIIClass
from agah.models.relationship import Relationship, RelationshipKind
from agah.models.scan import Scan, ScanStatus
from agah.models.source import DataSource, SamplingPolicy, SourceKind
from agah.pipeline.orchestrator import run_scan
from agah.security.crypto import encrypt

CASSETTE = json.loads(
    (Path(__file__).parent.parent / "fixtures/cassettes/describe_generic.json").read_text()
)
TEST_KEY = b"0" * 32


@pytest_asyncio.fixture
async def hr_source(session, hr_dsn, monkeypatch):
    monkeypatch.setattr("agah.pipeline.orchestrator.key_from_settings", lambda: TEST_KEY)
    source = DataSource(
        name="HR",
        kind=SourceKind.POSTGRES,
        config_encrypted=encrypt(json.dumps({"dsn": hr_dsn}), TEST_KEY),
        sampling_policy=SamplingPolicy.MASKED,
    )
    session.add(source)
    await session.flush()
    scan = Scan(data_source_id=source.id)
    session.add(scan)
    await session.flush()
    source.pending_scan_id = scan.id
    return source


@pytest.fixture
def stub_llm(monkeypatch):
    async def fake_call(session, task, messages, **kwargs):
        return Completion(
            text=json.dumps(CASSETTE), tokens_in=50, tokens_out=80,
            model="stub", provider="stub", latency_ms=1,
        )

    async def fake_embed(session, texts, scan_id=None):
        return [[0.0] * 1024 for _ in texts]

    monkeypatch.setattr("agah.pipeline.describe.call_task", fake_call)
    monkeypatch.setattr("agah.pipeline.embed.embed_texts", fake_embed)


@pytest.mark.asyncio
async def test_full_scan_creates_described_pending_entities(session, hr_source, stub_llm):
    scan = await run_scan(session, hr_source.pending_scan_id)

    assert scan.status is ScanStatus.SUCCEEDED
    entities = (
        await session.scalars(select(Entity).where(Entity.data_source_id == hr_source.id))
    ).all()
    names = {entity.name for entity in entities}
    assert {"employees", "departments", "leave_requests", "t_mst_01"} <= names
    assert all(entity.status is EntityStatus.PENDING for entity in entities)
    assert all(entity.description_ai is not None for entity in entities)
    assert all(entity.embedding is not None for entity in entities)


@pytest.mark.asyncio
async def test_scan_persists_inferred_relationship(session, hr_source, stub_llm):
    await run_scan(session, hr_source.pending_scan_id)
    inferred = (
        await session.scalars(
            select(Relationship).where(Relationship.kind == RelationshipKind.INFERRED)
        )
    ).all()
    assert any(relationship.from_field == "emp_id" for relationship in inferred)


@pytest.mark.asyncio
async def test_rescan_preserves_approved_entities(session, hr_source, stub_llm, monkeypatch):
    await run_scan(session, hr_source.pending_scan_id)

    employees = (
        await session.scalars(
            select(Entity).where(
                Entity.data_source_id == hr_source.id, Entity.name == "employees"
            )
        )
    ).one()
    employees.status = EntityStatus.APPROVED
    employees.description_human = {"summary": {"fa": "دست‌نویس من", "en": "my text"}}
    await session.flush()

    # Simulate drift: departments.name is retyped, nothing else changes. A retype
    # keeps the column queryable, so profiling still works against the real database.
    from agah.adapters.postgres import PostgresAdapter

    original = PostgresAdapter.introspect

    async def drifted(self):
        snapshot = await original(self)
        entities = []
        for entity in snapshot.entities:
            if entity.name == "departments":
                columns = tuple(
                    replace(column, data_type="VARCHAR(120)") if column.name == "name" else column
                    for column in entity.columns
                )
                entity = replace(entity, columns=columns)
            entities.append(entity)
        return replace(snapshot, entities=tuple(entities))

    monkeypatch.setattr(PostgresAdapter, "introspect", drifted)

    second_scan = Scan(data_source_id=hr_source.id)
    session.add(second_scan)
    await session.flush()
    result = await run_scan(session, second_scan.id)

    await session.refresh(employees)
    assert employees.status is EntityStatus.APPROVED
    assert employees.description_human["summary"]["fa"] == "دست‌نویس من"

    departments = (
        await session.scalars(
            select(Entity).where(
                Entity.data_source_id == hr_source.id, Entity.name == "departments"
            )
        )
    ).one()
    assert departments.status is EntityStatus.STALE
    assert result.status is ScanStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_describe_failure_isolates_to_one_entity(session, hr_source, stub_llm, monkeypatch):
    from agah.pipeline.describe import DescribeFailed, EntityDescription

    async def flaky(session_, entity, profile, neighbors, scan_id):
        if entity.name == "t_mst_01":
            raise DescribeFailed("model refused")
        return EntityDescription(
            summary={"fa": "الف", "en": "a"}, grain="row", business_domain="test",
            common_questions=[], fields=[], confidence=0.9,
        )

    monkeypatch.setattr("agah.pipeline.orchestrator.describe_entity", flaky)

    scan = await run_scan(session, hr_source.pending_scan_id)

    assert scan.status is ScanStatus.PARTIAL
    failed = (
        await session.scalars(
            select(Entity).where(
                Entity.data_source_id == hr_source.id,
                Entity.status == EntityStatus.DESCRIBE_FAILED,
            )
        )
    ).all()
    assert [entity.name for entity in failed] == ["t_mst_01"]


@pytest.mark.asyncio
async def test_embedding_failure_degrades_instead_of_discarding_the_scan(
    session, hr_source, monkeypatch
):
    """Embeddings serve S2 retrieval; losing them must not throw away descriptions.

    A self-hosted install with no local embedding service is a normal state, not
    a reason to discard a scan that cost real tokens to produce.
    """

    async def fake_call(session_, task, messages, **kwargs):
        return Completion(
            text=json.dumps(CASSETTE), tokens_in=50, tokens_out=80,
            model="stub", provider="stub", latency_ms=1,
        )

    async def unreachable_embedder(session_, texts, scan_id=None):
        raise ConnectionError("All connection attempts failed")

    monkeypatch.setattr("agah.pipeline.describe.call_task", fake_call)
    monkeypatch.setattr("agah.pipeline.embed.embed_texts", unreachable_embedder)

    scan = await run_scan(session, hr_source.pending_scan_id)

    assert scan.status is ScanStatus.PARTIAL
    assert "embed" in json.dumps(scan.error)

    entities = (
        await session.scalars(select(Entity).where(Entity.data_source_id == hr_source.id))
    ).all()
    assert entities, "descriptions were discarded along with the embeddings"
    assert all(entity.description_ai is not None for entity in entities)
    assert all(entity.embedding is None for entity in entities)


@pytest.mark.asyncio
async def test_scan_persists_the_profiler_pii_classification(session, hr_source, stub_llm):
    """The classification must reach the stored field, not just the prompt filter.

    Masking protects the LLM prompt, but the review UI and the knowledge export
    both read Field.pii_class. Leaving it at the default would tell a reviewer
    that a national ID column holds no personal data.
    """
    await run_scan(session, hr_source.pending_scan_id)

    employees = (
        await session.scalars(
            select(Entity).where(
                Entity.data_source_id == hr_source.id, Entity.name == "employees"
            )
        )
    ).one()
    fields = (
        await session.scalars(select(Field).where(Field.entity_id == employees.id))
    ).all()
    by_name = {field.name: field for field in fields}

    assert by_name["national_id"].pii_class is PIIClass.HIGH
    assert by_name["salary"].pii_class is PIIClass.HIGH
    assert by_name["mobile"].pii_class is PIIClass.LOW
    assert by_name["dept_id"].pii_class is PIIClass.NONE

    # Column statistics are what let a reviewer judge a description.
    assert by_name["dept_id"].stats is not None


@pytest.mark.asyncio
async def test_progress_events_cover_every_stage(session, hr_source, stub_llm):
    seen = []
    await run_scan(session, hr_source.pending_scan_id, progress=seen.append)
    stages = {event.stage for event in seen}
    assert stages == {"introspect", "profile", "probe", "describe", "embed", "diff"}
