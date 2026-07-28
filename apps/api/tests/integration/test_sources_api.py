import pytest


@pytest.mark.asyncio
async def test_create_source_never_echoes_dsn(client, admin_cookie, hr_dsn):
    response = await client.post(
        "/api/sources", cookies=admin_cookie,
        json={"name": "HR", "kind": "postgres", "dsn": hr_dsn},
    )
    assert response.status_code == 201
    body = response.json()
    assert "dsn" not in body
    assert "fixture" not in response.text  # the fixture database password
    assert body["status"] == "draft"


@pytest.mark.asyncio
async def test_list_sources_omits_credentials(client, admin_cookie, hr_dsn):
    await client.post(
        "/api/sources", cookies=admin_cookie,
        json={"name": "HR", "kind": "postgres", "dsn": hr_dsn},
    )
    response = await client.get("/api/sources", cookies=admin_cookie)
    assert response.status_code == 200
    assert "config_encrypted" not in response.text
    assert "postgresql" not in response.text


@pytest.mark.asyncio
async def test_test_connection_reports_failure_legibly(client, admin_cookie):
    response = await client.post(
        "/api/sources/test-connection", cookies=admin_cookie,
        json={"kind": "postgres", "dsn": "postgresql+asyncpg://nobody@127.0.0.1:1/none"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["healthy"] is False
    assert body["error"]


@pytest.mark.asyncio
async def test_trigger_scan_enqueues_job(client, admin_cookie, hr_dsn, fake_queue):
    created = await client.post(
        "/api/sources", cookies=admin_cookie,
        json={"name": "HR", "kind": "postgres", "dsn": hr_dsn},
    )
    source_id = created.json()["id"]

    response = await client.post(f"/api/sources/{source_id}/scans", cookies=admin_cookie)
    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert fake_queue.enqueued == [("scan_task", response.json()["id"])]


@pytest.mark.asyncio
async def test_analyst_cannot_create_source(client, analyst_cookie):
    response = await client.post(
        "/api/sources", cookies=analyst_cookie,
        json={"name": "x", "kind": "postgres", "dsn": "postgresql://x"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_unauthenticated_request_rejected(client):
    assert (await client.get("/api/sources")).status_code == 401


@pytest.mark.asyncio
async def test_scan_events_stream_emits_progress(client, admin_cookie, hr_dsn, fake_queue):
    created = await client.post(
        "/api/sources", cookies=admin_cookie,
        json={"name": "HR", "kind": "postgres", "dsn": hr_dsn},
    )
    scan = await client.post(
        f"/api/sources/{created.json()['id']}/scans", cookies=admin_cookie
    )
    scan_id = scan.json()["id"]

    async with client.stream(
        "GET", f"/api/scans/{scan_id}/events", cookies=admin_cookie
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        first = await anext(response.aiter_lines())
        assert first.startswith("data:")
