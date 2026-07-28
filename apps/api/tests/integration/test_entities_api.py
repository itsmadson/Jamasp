import pytest


@pytest.mark.asyncio
async def test_list_entities_filters_by_status(client, admin_cookie, scanned_source):
    response = await client.get(
        f"/api/sources/{scanned_source.id}/entities?status=pending", cookies=admin_cookie
    )
    assert response.status_code == 200
    assert all(item["status"] == "pending" for item in response.json()["items"])
    assert response.json()["items"]


@pytest.mark.asyncio
async def test_list_entities_sorts_low_confidence_first(client, admin_cookie, scanned_source):
    response = await client.get(
        f"/api/sources/{scanned_source.id}/entities?sort=confidence_asc", cookies=admin_cookie
    )
    scores = [
        item["confidence"] for item in response.json()["items"] if item["confidence"] is not None
    ]
    assert scores == sorted(scores)


@pytest.mark.asyncio
async def test_patch_stores_human_edit_without_destroying_ai_text(client, admin_cookie, entity):
    original_ai = entity.description_ai
    response = await client.patch(
        f"/api/entities/{entity.id}", cookies=admin_cookie,
        json={"description_human": {"summary": {"fa": "اصلاح شده", "en": "corrected"}}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["description_human"]["summary"]["fa"] == "اصلاح شده"
    assert body["description_ai"] == original_ai


@pytest.mark.asyncio
async def test_approve_records_reviewer_and_timestamp(client, admin_cookie, entity, admin_user):
    response = await client.post(f"/api/entities/{entity.id}/approve", cookies=admin_cookie)
    assert response.json()["status"] == "approved"
    assert response.json()["approved_by"] == str(admin_user.id)
    assert response.json()["approved_at"] is not None


@pytest.mark.asyncio
async def test_bulk_approve_respects_confidence_threshold(client, admin_cookie, scanned_source):
    response = await client.post(
        f"/api/sources/{scanned_source.id}/entities/bulk-approve",
        cookies=admin_cookie, json={"min_confidence": 0.9},
    )
    assert response.status_code == 200

    remaining = await client.get(
        f"/api/sources/{scanned_source.id}/entities?status=pending", cookies=admin_cookie
    )
    assert all(
        item["confidence"] is None or item["confidence"] < 0.9
        for item in remaining.json()["items"]
    )


@pytest.mark.asyncio
async def test_patching_field_meaning_updates_only_that_field(client, admin_cookie, entity):
    detail = (await client.get(f"/api/entities/{entity.id}", cookies=admin_cookie)).json()
    field_id = detail["fields"][0]["id"]

    response = await client.patch(
        f"/api/entities/{entity.id}", cookies=admin_cookie,
        json={"fields": [{"id": field_id, "meaning_human": {"fa": "شناسه", "en": "identifier"}}]},
    )
    assert response.status_code == 200
    fields = response.json()["fields"]
    changed = next(field for field in fields if field["id"] == field_id)
    assert changed["meaning_human"]["fa"] == "شناسه"
    assert all(
        field["meaning_human"] is None for field in fields if field["id"] != field_id
    )


@pytest.mark.asyncio
async def test_analyst_cannot_approve(client, analyst_cookie, entity):
    response = await client.post(f"/api/entities/{entity.id}/approve", cookies=analyst_cookie)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_ignore_excludes_entity_from_pending_work(client, admin_cookie, entity):
    await client.post(f"/api/entities/{entity.id}/ignore", cookies=admin_cookie)
    response = await client.get(f"/api/entities/{entity.id}", cookies=admin_cookie)
    assert response.json()["status"] == "ignored"
