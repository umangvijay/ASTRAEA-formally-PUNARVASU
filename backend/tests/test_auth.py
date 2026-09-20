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


async def test_tenant_api_key_works_platform_wide(app, client):
    """Audit MEDIUM: the console presents the tenant key as platform-wide ("shown
    only once") — JWT-gated routes like /api/auth/me must honor it too,
    authenticated as the tenant's owner account."""
    from app.core.models import Tenant, User
    from app.db import SessionLocal
    from app.sentinel.deps import generate_api_key, hash_api_key

    key = generate_api_key()
    async with SessionLocal() as db:
        tenant = Tenant(name="Keyed Tenant", api_key_hash=hash_api_key(key))
        db.add(tenant)
        await db.flush()
        db.add(User(tenant_id=tenant.id, email="keyed-owner@test.dev",
                    password_hash="x", full_name="Keyed Owner", role="owner"))
        await db.commit()

    me = await client.get("/api/auth/me", headers={"X-API-Key": key})
    assert me.status_code == 200, me.text
    assert me.json()["user"]["email"] == "keyed-owner@test.dev"
    assert me.json()["user"]["tenant"]["name"] == "Keyed Tenant"

    unknown = await client.get("/api/auth/me", headers={"X-API-Key": "pvu_unknown"})
    assert unknown.status_code == 401
    # garbage key must not fall through to "missing bearer token" semantics
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_api_key_rotation_is_role_gated(app, client):
    """Rotating the tenant key breaks every SENTINEL client — owners/admins
    decide that, never guests."""
    owner = await client.post("/api/auth/register", json={
        "email": "rot-owner@test.dev", "password": "Rotate-Key-1", "full_name": "Rot Owner"})
    owner_h = {"Authorization": f"Bearer {owner.json()['access_token']}"}
    ok = await client.post("/api/tenants/me/api-key", headers=owner_h)
    assert ok.status_code == 200 and ok.json()["api_key"].startswith("pvu_")

    guest = await client.post("/api/auth/guest")
    assert guest.status_code == 201
    guest_h = {"Authorization": f"Bearer {guest.json()['access_token']}"}
    denied = await client.post("/api/tenants/me/api-key", headers=guest_h)
    assert denied.status_code == 403
