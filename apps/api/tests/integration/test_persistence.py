"""Writes must survive the request that made them.

The API previously only flushed, so every POST was rolled back when the session
closed. Same-request assertions cannot catch that; these read back in a *second*
request, which is the only thing that proves a commit happened.
"""

import pytest


@pytest.mark.asyncio
async def test_created_source_is_visible_to_a_later_request(client, admin_cookie, hr_dsn):
    created = await client.post(
        "/api/sources",
        cookies=admin_cookie,
        json={"name": "HR", "kind": "postgres", "dsn": hr_dsn},
    )
    assert created.status_code == 201
    source_id = created.json()["id"]

    fetched = await client.get(f"/api/sources/{source_id}", cookies=admin_cookie)
    assert fetched.status_code == 200, "source vanished after the creating request ended"
    assert fetched.json()["name"] == "HR"

    listed = await client.get("/api/sources", cookies=admin_cookie)
    assert source_id in {row["id"] for row in listed.json()}


@pytest.mark.asyncio
async def test_approval_is_visible_to_a_later_request(client, admin_cookie, entity):
    approved = await client.post(f"/api/entities/{entity.id}/approve", cookies=admin_cookie)
    assert approved.status_code == 200

    fetched = await client.get(f"/api/entities/{entity.id}", cookies=admin_cookie)
    assert fetched.json()["status"] == "approved"
    assert fetched.json()["approved_at"] is not None
