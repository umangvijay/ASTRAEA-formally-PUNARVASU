from __future__ import annotations


async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["app"] == "astraea"
    assert body["phase"] == 7  # current build phase
    assert "vertex_ready" in body
    assert "llm" in body


async def test_health_head_ok(client):
    resp = await client.head("/health")
    assert resp.status_code == 200


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


async def test_workspace_unknown_module_is_422_not_500(client, auth_headers):
    """Audit HIGH-4: {"mode":"solo","module":"warp-drive"} used to 500 on an
    uncaught ValueError from workspace.set_mode. A bad module name is a 422."""
    resp = await client.put("/api/workspace", headers=auth_headers,
                            json={"mode": "solo", "module": "warp-drive"})
    assert resp.status_code == 422
    assert "warp-drive" in resp.json()["detail"]
