"""The dashboard's single request.

The value here is `next_step`: the dashboard shows one call to action per source,
and a wrong one sends the user to a page that cannot help them yet.
"""

import json

import pytest
import pytest_asyncio

from jamasp.models.entity import Entity, EntityStatus
from jamasp.models.query import Query, QueryStatus
from jamasp.models.source import DataSource, SamplingPolicy, SourceKind, SourceStatus
from jamasp.security.crypto import encrypt

TEST_KEY = b"0" * 32


@pytest_asyncio.fixture
async def source(session):
    row = DataSource(
        name="warehouse",
        kind=SourceKind.POSTGRES,
        config_encrypted=encrypt(json.dumps({"dsn": "postgresql://x/y"}), TEST_KEY),
        sampling_policy=SamplingPolicy.MASKED,
    )
    session.add(row)
    await session.flush()
    return row


async def _entity(session, source, name: str, status: EntityStatus):
    entity = Entity(
        data_source_id=source.id,
        schema_name="public",
        name=name,
        kind="table",
        status=status,
        structural={},
        structural_hash=name,
    )
    session.add(entity)
    await session.flush()
    return entity


async def _fetch(client, admin_cookie):
    response = await client.get("/api/overview", cookies=admin_cookie)
    assert response.status_code == 200
    return response.json()


@pytest.mark.asyncio
async def test_a_source_with_no_entities_is_told_to_scan(client, admin_cookie, source):
    body = await _fetch(client, admin_cookie)
    entry = next(item for item in body["sources"] if item["id"] == str(source.id))
    assert entry["next_step"] == "scan"


@pytest.mark.asyncio
async def test_a_scanned_source_with_pending_entities_is_told_to_review(
    client, admin_cookie, session, source
):
    await _entity(session, source, "orders", EntityStatus.PENDING)
    await _entity(session, source, "customers", EntityStatus.APPROVED)

    entry = next(
        item
        for item in (await _fetch(client, admin_cookie))["sources"]
        if item["id"] == str(source.id)
    )
    assert entry["next_step"] == "review"
    assert entry["entities_total"] == 2
    assert entry["entities_pending"] == 1
    assert entry["entities_approved"] == 1


@pytest.mark.asyncio
async def test_a_stale_entity_counts_as_needing_review(
    client, admin_cookie, session, source
):
    """Drift is a reason to look again, so it belongs in the same count."""
    await _entity(session, source, "orders", EntityStatus.APPROVED)
    await _entity(session, source, "customers", EntityStatus.STALE)

    entry = next(
        item
        for item in (await _fetch(client, admin_cookie))["sources"]
        if item["id"] == str(source.id)
    )
    assert entry["entities_pending"] == 1
    assert entry["next_step"] == "review"


@pytest.mark.asyncio
async def test_a_fully_approved_source_is_told_to_ask(
    client, admin_cookie, session, source
):
    await _entity(session, source, "orders", EntityStatus.APPROVED)

    entry = next(
        item
        for item in (await _fetch(client, admin_cookie))["sources"]
        if item["id"] == str(source.id)
    )
    assert entry["next_step"] == "ask"


@pytest.mark.asyncio
async def test_a_source_already_in_use_needs_nothing(
    client, admin_cookie, session, source
):
    await _entity(session, source, "orders", EntityStatus.APPROVED)
    session.add(
        Query(
            data_source_id=source.id,
            question="how many orders?",
            locale="fa",
            status=QueryStatus.SUCCEEDED,
        )
    )
    await session.flush()

    entry = next(
        item
        for item in (await _fetch(client, admin_cookie))["sources"]
        if item["id"] == str(source.id)
    )
    assert entry["next_step"] == "ready"
    assert entry["questions"] == 1


@pytest.mark.asyncio
async def test_a_scan_in_flight_says_so_rather_than_asking_for_another(
    client, admin_cookie, session, source
):
    source.status = SourceStatus.SCANNING
    await session.flush()

    entry = next(
        item
        for item in (await _fetch(client, admin_cookie))["sources"]
        if item["id"] == str(source.id)
    )
    assert entry["next_step"] == "scanning"


@pytest.mark.asyncio
async def test_recent_activity_mixes_questions_and_reports_newest_first(
    client, admin_cookie, session, source
):
    for index in range(3):
        session.add(
            Query(
                data_source_id=source.id,
                question=f"question {index}",
                locale="fa",
                status=QueryStatus.SUCCEEDED,
            )
        )
    await session.flush()

    body = await _fetch(client, admin_cookie)
    assert [item["kind"] for item in body["recent"]] == ["question"] * 3
    stamps = [item["created_at"] for item in body["recent"]]
    assert stamps == sorted(stamps, reverse=True)


@pytest.mark.asyncio
async def test_totals_are_summed_across_sources(client, admin_cookie, session, source):
    await _entity(session, source, "orders", EntityStatus.APPROVED)
    await _entity(session, source, "customers", EntityStatus.PENDING)

    totals = (await _fetch(client, admin_cookie))["totals"]
    assert totals["sources"] >= 1
    assert totals["entities"] >= 2
    assert totals["approved"] >= 1
    assert totals["pending"] >= 1


@pytest.mark.asyncio
async def test_archived_entities_are_not_counted_as_work(
    client, admin_cookie, session, source
):
    """An archived table is gone from the source; counting it would overstate."""
    await _entity(session, source, "orders", EntityStatus.APPROVED)
    await _entity(session, source, "dropped_table", EntityStatus.ARCHIVED)

    entry = next(
        item
        for item in (await _fetch(client, admin_cookie))["sources"]
        if item["id"] == str(source.id)
    )
    assert entry["entities_total"] == 1


@pytest.mark.asyncio
async def test_the_overview_needs_a_session(client):
    response = await client.get("/api/overview")
    assert response.status_code == 401
