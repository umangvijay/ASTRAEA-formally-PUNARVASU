"""LOOM gate: provenance stamps, usage trails, sharing matrix, org profile — the anti-re-onboarding system."""

from __future__ import annotations

from app.db import SessionLocal
from app.loom import service
from app.loom.models import LoomItem, LoomUsage
from sqlalchemy import select


async def test_cross_module_provenance_and_usage_stamp(client, auth_headers):
    # SHIELD writes an incident into LOOM
    created = (
        await client.post(
            "/api/loom/items",
            headers={**auth_headers, "X-Module": "shield"},
            json={"kind": "incident", "title": "Brute force on db-1",
                  "summary": "SSH brute force detected on host db-1",
                  "payload": {"host": "db-1", "severity": "high"}},
        )
    ).json()
    assert created["provenance"]["from"] == "FROM SHIELD"
    assert created["used_by"] == []

    # MEDIC (months later, fresh session) asks for its context — it must already know
    ctx = (await client.get("/api/loom/context?module=medic", headers=auth_headers)).json()
    titles = [i["title"] for i in ctx["items"]]
    assert "Brute force on db-1" in titles
    item = next(i for i in ctx["items"] if i["title"] == "Brute force on db-1")
    assert item["provenance"]["from"] == "FROM SHIELD"
    assert "medic" in item["used_by"]  # the read stamped the usage

    # OPERATOR reads next — sees the trail left by MEDIC
    ctx2 = (await client.get("/api/loom/context?module=operator", headers=auth_headers)).json()
    item2 = next(i for i in ctx2["items"] if i["title"] == "Brute force on db-1")
    assert "medic" in item2["used_by"] and "operator" in item2["used_by"]


async def test_sharing_matrix_revocation(client, auth_headers):
    await client.post(
        "/api/loom/items", headers={**auth_headers, "X-Module": "shield"},
        json={"kind": "incident", "title": "Secret incident"},
    )
    await client.patch("/api/loom/sharing", headers=auth_headers,
                       json={"module": "operator", "may_read": False})

    ctx_operator = (await client.get("/api/loom/context?module=operator", headers=auth_headers)).json()
    assert ctx_operator["items"] == []  # revoked module sees nothing

    ctx_medic = (await client.get("/api/loom/context?module=medic", headers=auth_headers)).json()
    assert any(i["title"] == "Secret incident" for i in ctx_medic["items"])

    matrix = (await client.get("/api/loom/sharing", headers=auth_headers)).json()["matrix"]
    assert matrix["operator"] is False and matrix["medic"] is True


async def test_share_with_scoping(client, auth_headers):
    await client.post(
        "/api/loom/items", headers={**auth_headers, "X-Module": "forge"},
        json={"kind": "skill", "title": "Operator-only skill", "share_with": ["operator"]},
    )
    ctx_operator = (await client.get("/api/loom/context?module=operator", headers=auth_headers)).json()
    assert any(i["title"] == "Operator-only skill" for i in ctx_operator["items"])
    ctx_shield = (await client.get("/api/loom/context?module=shield", headers=auth_headers)).json()
    assert not any(i["title"] == "Operator-only skill" for i in ctx_shield["items"])


async def test_org_profile_filled_once(client, auth_headers):
    resp = await client.put(
        "/api/loom/profile", headers=auth_headers,
        json={"content": {"company": "Acme Robotics", "stack": ["fastapi", "postgres"],
                          "compliance": ["DPDP-2023"]}},
    )
    assert resp.status_code == 200
    again = (await client.get("/api/loom/profile", headers=auth_headers)).json()["profile"]
    assert again["company"] == "Acme Robotics"


async def test_unknown_module_rejected(client, auth_headers):
    resp = await client.post(
        "/api/loom/items", headers={**auth_headers, "X-Module": "not-a-module"},
        json={"kind": "note", "title": "x"},
    )
    assert resp.status_code == 422


async def test_engine_loom_write_carries_run_provenance(app):
    """Items written by runs keep their origin_run_id — replayable to the exact run."""
    from app.core import engine
    from app.core.models import Run
    from app.core.models import Tenant as T

    async with SessionLocal() as db:
        tenant = T(name="loom-prov-test")
        db.add(tenant)
        await db.commit()
        await db.refresh(tenant)
        run = Run(tenant_id=tenant.id, goal="record a fact",
                  workflow=engine.validate_workflow([
                      {"name": "remember", "type": "loom_write", "title": "Fact",
                       "content": "the sky is blue", "kind": "artifact"}]),
                  origin_module="medic")
        db.add(run)
        await db.commit()
        await db.refresh(run)
        run_id = run.id

    await engine.execute(run_id)
    async with SessionLocal() as db:
        item = (await db.execute(
            select(LoomItem).where(LoomItem.origin_run_id == run_id)
        )).scalar_one()
        assert item.origin_module == "medic"
        assert item.payload["content"] == "the sky is blue"
