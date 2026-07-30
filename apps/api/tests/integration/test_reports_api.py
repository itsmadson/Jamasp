"""The HTTP contract the browser depends on."""

import json

import pytest
import pytest_asyncio

from jamasp.models.report import Report, ReportStatus
from jamasp.models.source import DataSource, SamplingPolicy, SourceKind
from jamasp.security.crypto import encrypt

TEST_KEY = b"0" * 32


@pytest_asyncio.fixture
async def source(session):
    row = DataSource(
        name="HR",
        kind=SourceKind.POSTGRES,
        config_encrypted=encrypt(json.dumps({"dsn": "postgresql://x/y"}), TEST_KEY),
        sampling_policy=SamplingPolicy.MASKED,
    )
    session.add(row)
    await session.flush()
    return row


@pytest.mark.asyncio
async def test_creating_a_report_returns_at_once_and_queues_the_build(
    client, admin_cookie, source, fake_queue
):
    """Building takes minutes; the request must not wait for it.

    Holding the request open is what produced a proxy timeout the user read as a
    crash, while the work completed and the report appeared on reload.
    """
    response = await client.post(
        f"/api/sources/{source.id}/reports",
        json={"question": "users by role", "locale": "fa"},
        cookies=admin_cookie,
    )

    assert response.status_code == 202
    body = response.json()
    # The wire value, not the Python enum's repr: the client compares this string.
    assert body["status"] == "queued"
    assert body["question"] == "users by role"
    assert body["spec"]["blocks"] == []

    assert fake_queue.enqueued == [("report_task", body["id"])]


@pytest.mark.asyncio
async def test_a_report_still_building_reports_its_status(
    client, admin_cookie, session, source
):
    report = Report(
        data_source_id=source.id,
        question="anything",
        locale="fa",
        title={"fa": "x", "en": "x"},
        spec={"schema_version": "2.0", "title": {"fa": "x", "en": "x"},
              "summary": {"fa": "", "en": ""}, "blocks": [], "datasets": []},
        status=ReportStatus.RUNNING,
    )
    session.add(report)
    await session.flush()

    response = await client.get(f"/api/reports/{report.id}", cookies=admin_cookie)

    assert response.status_code == 200
    assert response.json()["status"] == "running"


@pytest.mark.asyncio
async def test_each_panel_comes_back_as_its_own_dataset(
    client, admin_cookie, session, source
):
    """The browser needs the panels kept apart to draw them apart."""
    report = Report(
        data_source_id=source.id,
        question="two things",
        locale="fa",
        title={"fa": "x", "en": "x"},
        spec={
            "schema_version": "2.0",
            "title": {"fa": "x", "en": "x"},
            "summary": {"fa": "", "en": ""},
            "blocks": [],
            "datasets": [
                {"key": "by_role", "query_id": None, "question": "by role",
                 "explanation": None},
                {"key": "monthly", "query_id": None, "question": "monthly",
                 "explanation": None},
            ],
        },
        status=ReportStatus.SUCCEEDED,
    )
    session.add(report)
    await session.flush()

    response = await client.get(
        f"/api/reports/{report.id}?refresh=false", cookies=admin_cookie
    )

    assert response.status_code == 200
    body = response.json()
    assert [dataset["key"] for dataset in body["datasets"]] == ["by_role", "monthly"]
