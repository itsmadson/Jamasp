import pytest


@pytest.mark.asyncio
async def test_get_returns_defaults_before_configuration(client, admin_cookie):
    response = await client.get("/api/settings/llm", cookies=admin_cookie)
    assert response.status_code == 200
    assert (
        response.json()["routes"]["describe_entity"]["model"]
        == "nvidia/nemotron-3-ultra-550b-a55b:free"
    )


@pytest.mark.asyncio
async def test_api_key_is_redacted_on_read(client, admin_cookie):
    await client.put(
        "/api/settings/llm/providers", cookies=admin_cookie,
        json={
            "providers": {
                "openrouter": {
                    "base_url": "https://openrouter.ai/api/v1",
                    "api_key": "sk-or-v1-supersecret",
                }
            }
        },
    )
    response = await client.get("/api/settings/llm", cookies=admin_cookie)
    assert "supersecret" not in response.text
    assert response.json()["providers"]["openrouter"]["api_key"] == "••••••••"


@pytest.mark.asyncio
async def test_switching_describe_model_to_local_requires_no_code_change(client, admin_cookie):
    response = await client.put(
        "/api/settings/llm/routes", cookies=admin_cookie,
        json={
            "routes": {
                "describe_entity": {
                    "provider": "local", "model": "qwen2.5:32b",
                    "temperature": 0.1, "fallbacks": [],
                }
            }
        },
    )
    assert response.status_code == 200

    updated = await client.get("/api/settings/llm", cookies=admin_cookie)
    assert updated.json()["routes"]["describe_entity"]["provider"] == "local"
    assert updated.json()["routes"]["describe_entity"]["model"] == "qwen2.5:32b"


@pytest.mark.asyncio
async def test_analyst_cannot_change_provider_settings(client, analyst_cookie):
    response = await client.put(
        "/api/settings/llm/providers", cookies=analyst_cookie, json={"providers": {}}
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_unknown_task_name_rejected(client, admin_cookie):
    response = await client.put(
        "/api/settings/llm/routes", cookies=admin_cookie,
        json={"routes": {"not_a_task": {"provider": "local", "model": "x"}}},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_stored_api_key_is_encrypted_at_rest(client, admin_cookie, session):
    from sqlalchemy import select

    from jamasp.models.observability import Setting

    await client.put(
        "/api/settings/llm/providers", cookies=admin_cookie,
        json={"providers": {"gapgpt": {"base_url": "https://x/v1", "api_key": "sk-plain"}}},
    )
    row = (
        await session.scalars(select(Setting).where(Setting.key == "llm_providers"))
    ).one()
    assert "sk-plain" not in str(row.value)
