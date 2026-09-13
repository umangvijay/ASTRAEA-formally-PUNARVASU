from __future__ import annotations


async def test_register_login_me(client):
    resp = await client.post(
        "/api/auth/register",
        json={"email": "a@b.dev", "password": "LongEnough-PW-1", "full_name": "Test User"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["access_token"]
    assert body["user"]["email"] == "a@b.dev"
    assert body["user"]["tenant"]["name"] == "Test's Workspace"  # personal tenant, auto-created

    resp = await client.post(
        "/api/auth/login", json={"email": "a@b.dev", "password": "LongEnough-PW-1"}
    )
    assert resp.status_code == 200
    token = resp.json()["access_token"]

    resp = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["user"]["email"] == "a@b.dev"


async def test_register_duplicate_email_conflict(client):
    payload = {"email": "dup@b.dev", "password": "LongEnough-PW-1", "full_name": "Dup User"}
    assert (await client.post("/api/auth/register", json=payload)).status_code == 201
    assert (await client.post("/api/auth/register", json=payload)).status_code == 409


async def test_login_wrong_password_401(client):
    await client.post(
        "/api/auth/register",
        json={"email": "c@b.dev", "password": "LongEnough-PW-1", "full_name": "C User"},
    )
    resp = await client.post(
        "/api/auth/login", json={"email": "c@b.dev", "password": "Wrong-Password-1"}
    )
    assert resp.status_code == 401


async def test_me_requires_token(client):
    assert (await client.get("/api/auth/me")).status_code == 401
    assert (
        await client.get("/api/auth/me", headers={"Authorization": "Bearer garbage"})
    ).status_code == 401
