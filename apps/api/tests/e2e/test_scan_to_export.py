import pytest


@pytest.mark.asyncio
async def test_export_contains_only_approved_entities(client, admin_cookie, scanned_source):
    response = await client.get(
        f"/api/sources/{scanned_source.id}/knowledge", cookies=admin_cookie
    )
    assert response.status_code == 200
    assert response.json()["entities"] == []  # nothing approved yet


@pytest.mark.asyncio
async def test_full_cycle_scan_approve_export(client, admin_cookie, scanned_source):
    """The S1 acceptance test: register -> scan -> approve -> export."""
    await client.post(
        f"/api/sources/{scanned_source.id}/entities/bulk-approve",
        cookies=admin_cookie, json={"min_confidence": 0.0},
    )

    response = await client.get(
        f"/api/sources/{scanned_source.id}/knowledge", cookies=admin_cookie
    )
    body = response.json()

    assert body["schema_version"] == "1.0"
    assert body["source"]["dialect"] == "postgres"
    names = {entity["name"] for entity in body["entities"]}
    assert {"employees", "departments", "leave_requests"} <= names

    leave = next(entity for entity in body["entities"] if entity["name"] == "leave_requests")
    assert leave["summary"]["fa"] and leave["summary"]["en"]
    status_field = next(field for field in leave["fields"] if field["name"] == "status")
    assert status_field["enum_map"]["2"]["en"] == "approved"
    assert any(
        relationship["kind"] == "inferred" and relationship["from"] == "emp_id"
        for relationship in leave["relationships"]
    )


@pytest.mark.asyncio
async def test_export_prefers_human_text_over_ai_text(client, admin_cookie, scanned_source):
    listing = await client.get(
        f"/api/sources/{scanned_source.id}/entities", cookies=admin_cookie
    )
    target = next(
        item for item in listing.json()["items"] if item["name"] == "employees"
    )
    await client.patch(
        f"/api/entities/{target['id']}", cookies=admin_cookie,
        json={"description_human": {"summary": {"fa": "کارکنان شرکت", "en": "Company staff"}}},
    )
    await client.post(f"/api/entities/{target['id']}/approve", cookies=admin_cookie)

    body = (
        await client.get(f"/api/sources/{scanned_source.id}/knowledge", cookies=admin_cookie)
    ).json()
    employees = next(entity for entity in body["entities"] if entity["name"] == "employees")
    assert employees["summary"]["fa"] == "کارکنان شرکت"


@pytest.mark.asyncio
async def test_export_excludes_ignored_entities(client, admin_cookie, scanned_source):
    listing = await client.get(
        f"/api/sources/{scanned_source.id}/entities", cookies=admin_cookie
    )
    legacy = next(item for item in listing.json()["items"] if item["name"] == "t_mst_01")
    await client.post(f"/api/entities/{legacy['id']}/ignore", cookies=admin_cookie)
    await client.post(
        f"/api/sources/{scanned_source.id}/entities/bulk-approve",
        cookies=admin_cookie, json={"min_confidence": 0.0},
    )

    body = (
        await client.get(f"/api/sources/{scanned_source.id}/knowledge", cookies=admin_cookie)
    ).json()
    assert "t_mst_01" not in {entity["name"] for entity in body["entities"]}


@pytest.mark.asyncio
async def test_export_never_contains_raw_pii(client, admin_cookie, scanned_source):
    await client.post(
        f"/api/sources/{scanned_source.id}/entities/bulk-approve",
        cookies=admin_cookie, json={"min_confidence": 0.0},
    )
    body = (
        await client.get(f"/api/sources/{scanned_source.id}/knowledge", cookies=admin_cookie)
    ).text
    for secret in ("0079542619", "09121234567", "120000000"):
        assert secret not in body


@pytest.mark.asyncio
async def test_export_omits_relationships_to_unapproved_tables(
    client, admin_cookie, scanned_source
):
    listing = await client.get(
        f"/api/sources/{scanned_source.id}/entities", cookies=admin_cookie
    )
    leave = next(item for item in listing.json()["items"] if item["name"] == "leave_requests")
    await client.post(f"/api/entities/{leave['id']}/approve", cookies=admin_cookie)

    body = (
        await client.get(f"/api/sources/{scanned_source.id}/knowledge", cookies=admin_cookie)
    ).json()
    exported = next(
        entity for entity in body["entities"] if entity["name"] == "leave_requests"
    )
    # employees was never approved, so the inferred link to it must not be exported.
    assert exported["relationships"] == []
