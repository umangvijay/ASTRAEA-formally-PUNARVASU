"""Cross-module integration tests — the 5 flows from MASTER_SPEC §3.C.

These test the LOOM context fabric as the integration layer between modules:
1. SHIELD → MEDIC: incident context flows from SHIELD to MEDIC via LOOM
2. VAANI docs → MEDIC/SHIELD: documents uploaded for VAANI are retrievable by others
3. SHIELD vulnerability → MEDIC PR: SHIELD findings cited in MEDIC's PR description
4. OPERATOR trajectory → VAANI: learned UI trajectories reusable by VAANI
5. FORGE skills → all agents: mined skills available to all modules

Each test creates real data in one module's LOOM scope and verifies it appears
in another module's context query — with correct provenance stamps.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.loom.service import context_for, write_item


TENANT = "test-cross-module"


@pytest_asyncio.fixture
async def db(db_session: AsyncSession):
    """Alias the conftest session."""
    yield db_session


# ── Flow 1: SHIELD incident → MEDIC context ────────────────────────────────

@pytest.mark.asyncio
async def test_shield_incident_visible_to_medic(db: AsyncSession):
    """When SHIELD writes an incident to LOOM, MEDIC should see it in its context."""
    # SHIELD writes incident
    item = await write_item(
        db,
        tenant_id=TENANT,
        origin_module="shield",
        kind="incident",
        title="SOC incident: brute force on db-1",
        summary="Detected 47 login failures from 10.0.1.99 followed by a successful login. "
                "Mapped to T1110 (Brute Force). Containment pending.",
        payload={"host": "db-1", "attacker_ip": "10.0.1.99", "techniques": ["T1110"]},
        share_with=["medic", "operator", "forge"],
    )
    assert item.id

    # MEDIC queries its context
    ctx = await context_for(db, tenant_id=TENANT, module="medic", kinds=["incident"])
    assert len(ctx) >= 1

    found = next((c for c in ctx if "brute force" in c["title"].lower()), None)
    assert found is not None, "MEDIC should see SHIELD's incident"
    assert found["origin_module"] == "shield"
    # the affected host lives in the title + structured payload (not the prose summary)
    assert "db-1" in found["title"] or found.get("payload", {}).get("host") == "db-1"


# ── Flow 2: VAANI docs → MEDIC/SHIELD retrieval ───────────────────────────

@pytest.mark.asyncio
async def test_vaani_docs_visible_to_medic_and_shield(db: AsyncSession):
    """Documents uploaded for VAANI should be retrievable by MEDIC and SHIELD."""
    await write_item(
        db,
        tenant_id=TENANT,
        origin_module="vaani",
        kind="knowledge",
        title="Company refund policy",
        summary="Full refund within 7 days. Partial refund within 30 days. "
                "No refund after 30 days. Escalation to manager for orders over ₹50,000.",
        payload={"doc_type": "policy", "language": "en"},
        share_with=["medic", "shield", "operator"],
    )

    # MEDIC can see it
    medic_ctx = await context_for(db, tenant_id=TENANT, module="medic", kinds=["knowledge"])
    refund_docs = [c for c in medic_ctx if "refund" in c["title"].lower()]
    assert len(refund_docs) >= 1, "MEDIC should see VAANI's knowledge docs"
    assert refund_docs[0]["origin_module"] == "vaani"

    # SHIELD can see it
    shield_ctx = await context_for(db, tenant_id=TENANT, module="shield", kinds=["knowledge"])
    refund_docs = [c for c in shield_ctx if "refund" in c["title"].lower()]
    assert len(refund_docs) >= 1, "SHIELD should see VAANI's knowledge docs"


# ── Flow 3: SHIELD vulnerability → MEDIC gets context ─────────────────────

@pytest.mark.asyncio
async def test_shield_vuln_available_for_medic_investigation(db: AsyncSession):
    """A SHIELD vulnerability finding should be available as context for MEDIC's investigator."""
    await write_item(
        db,
        tenant_id=TENANT,
        origin_module="shield",
        kind="vulnerability",
        title="CVE-2024-1234: RCE in payment-service v2.3",
        summary="Remote code execution via deserialization in /api/v2/webhooks. "
                "CVSS 9.8. Patch available: upgrade to v2.4.",
        payload={"cve": "CVE-2024-1234", "service": "payment-service", "cvss": 9.8},
        share_with=["medic", "forge"],
    )

    medic_ctx = await context_for(db, tenant_id=TENANT, module="medic")
    vuln = next((c for c in medic_ctx if "CVE-2024-1234" in c.get("title", "")), None)
    assert vuln is not None, "MEDIC should see SHIELD's vulnerability finding"
    assert vuln["origin_module"] == "shield"


# ── Flow 4: OPERATOR trajectory → available to VAANI ──────────────────────

@pytest.mark.asyncio
async def test_operator_trajectory_reusable_by_vaani(db: AsyncSession):
    """A successful OPERATOR trajectory should be available for VAANI to replay."""
    trajectory = [
        {"action": "navigate", "url": "https://portal.example.com/login"},
        {"action": "type", "element": 12, "text": "admin@example.com"},
        {"action": "type", "element": 14, "text": "password123"},
        {"action": "click", "element": 16, "reason": "submit login form"},
        {"action": "click", "element": 22, "reason": "navigate to bookings"},
    ]
    await write_item(
        db,
        tenant_id=TENANT,
        origin_module="operator",
        kind="trajectory",
        title="Login and navigate to bookings on portal.example.com",
        summary="5-step trajectory: login → navigate to bookings page. "
                "Success rate: 100% over 3 runs.",
        payload={"steps": trajectory, "url": "https://portal.example.com", "success_rate": 1.0},
        share_with=["vaani", "forge"],
    )

    vaani_ctx = await context_for(db, tenant_id=TENANT, module="vaani", kinds=["trajectory"])
    traj = next((c for c in vaani_ctx if "portal.example.com" in c.get("title", "")), None)
    assert traj is not None, "VAANI should see OPERATOR's trajectory"
    assert traj["origin_module"] == "operator"


# ── Flow 5: FORGE skills → all agents ─────────────────────────────────────

@pytest.mark.asyncio
async def test_forge_skills_available_to_all_agents(db: AsyncSession):
    """Skills learned by FORGE from MEDIC failures should be offered to all agents."""
    await write_item(
        db,
        tenant_id=TENANT,
        origin_module="forge",
        kind="skill",
        title="Improved SQL query generation for inventory service",
        summary="Learned from 12 MEDIC failures: the inventory service uses a non-standard "
                "schema with composite keys. Updated prompt template achieves 94% accuracy.",
        payload={
            "capability": "sql-writer",
            "eval_score": 0.94,
            "source_failures": 12,
            "prompt_template": "Schema has composite keys on (tenant_id, item_id)...",
        },
        share_with=["medic", "operator", "shield", "vaani"],
    )

    # Every module should see it
    for module in ("medic", "operator", "shield", "vaani"):
        ctx = await context_for(db, tenant_id=TENANT, module=module, kinds=["skill"])
        skill = next((c for c in ctx if "sql query generation" in c.get("title", "").lower()), None)
        assert skill is not None, f"{module.upper()} should see FORGE's skill"
        assert skill["origin_module"] == "forge"


# ── Provenance isolation test ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_unshared_module_cannot_see_item(db: AsyncSession):
    """An item NOT shared with a module should NOT appear in that module's context."""
    await write_item(
        db,
        tenant_id=TENANT,
        origin_module="shield",
        kind="classified",
        title="Internal SOC notes — not for VAANI",
        summary="Sensitive investigation details for SOC team only.",
        payload={},
        share_with=["medic"],  # explicitly NOT shared with vaani
    )

    vaani_ctx = await context_for(db, tenant_id=TENANT, module="vaani", kinds=["classified"])
    classified = [c for c in vaani_ctx if "Internal SOC notes" in c.get("title", "")]
    assert len(classified) == 0, "VAANI should NOT see items not shared with it"

    # But MEDIC should
    medic_ctx = await context_for(db, tenant_id=TENANT, module="medic", kinds=["classified"])
    classified = [c for c in medic_ctx if "Internal SOC notes" in c.get("title", "")]
    assert len(classified) >= 1, "MEDIC should see items shared with it"
