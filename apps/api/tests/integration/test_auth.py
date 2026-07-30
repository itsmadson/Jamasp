import pytest


@pytest.mark.asyncio
async def test_login_sets_httponly_cookie(client, admin_user):
    response = await client.post(
        "/api/auth/login", json={"email": admin_user.email, "password": "correct-horse"}
    )
    assert response.status_code == 200
    set_cookie = response.headers["set-cookie"]
    assert "jamasp_session" in set_cookie
    assert "HttpOnly" in set_cookie


@pytest.mark.asyncio
async def test_login_rejects_wrong_password(client, admin_user):
    response = await client.post(
        "/api/auth/login", json={"email": admin_user.email, "password": "wrong"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_password_hash_never_returned(client, admin_cookie):
    response = await client.get("/api/auth/me", cookies=admin_cookie)
    assert response.status_code == 200
    assert "password" not in response.text.lower()
    assert response.json()["role"] == "admin"


@pytest.mark.asyncio
async def test_expired_or_forged_cookie_rejected(client):
    response = await client.get("/api/auth/me", cookies={"jamasp_session": "not.a.jwt"})
    assert response.status_code == 401


# Role enforcement on admin-only routes is covered in test_sources_api.py, where
# those routes exist.
