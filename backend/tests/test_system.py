from __future__ import annotations


async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["app"] == "astraea"
    assert body["phase"] == 7  # current build phase


async def test_ready(client):
    resp = await client.get("/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"


async def test_modules_registry(client):
    resp = await client.get("/api/modules")
    assert resp.status_code == 200
    body = resp.json()
    codenames = {m["codename"] for m in body["modules"]}
    assert codenames == {"medic", "operator", "shield", "vaani", "forge", "model_forge"}
    services = {s["codename"] for s in body["core_services"]}
    assert services == {"sentinel", "loom", "pulse"}
    # nothing hardcoded as UP in phase 0 — everything reports its landing phase
    assert all(m["status"].startswith("phase-") for m in body["modules"])
