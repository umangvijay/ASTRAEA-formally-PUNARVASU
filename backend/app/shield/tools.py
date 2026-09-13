"""SHIELD agent tools, executed as steps of a durable run through the core engine.

- shield.correlate: turns raw events + rule hits into an incident narrative with MITRE
  ATT&CK mapping (LLM via SENTINEL when available; the fallback assembles the narrative
  from the actual detected facts — real data, real techniques, no invented story).
- shield.graph:      builds the attack graph (who reached what, labelled with techniques).
- shield.contain:    applies the approved containment to the lab (block IP / lock user)
                     and records exactly what was done.
"""

from __future__ import annotations

import datetime as dt
import json
import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shield.graph import blast_radius, save_graph
from app.shield.models import SecurityEvent, ShieldIncident


async def dispatch(db: AsyncSession, run, name: str, args: dict) -> dict:
    if name == "shield.correlate":
        return await _correlate(db, run, args)
    if name == "shield.graph":
        return await _graph(db, run, args)
    if name == "shield.contain":
        return await _contain(db, run, args)
    if name == "shield.blast_radius":
        return await _blast_radius(db, run, args)
    raise ValueError(f"unknown shield tool '{name}'")


async def _blast_radius(db: AsyncSession, run, args: dict) -> dict:
    """What could the attacker reach from the entry point? (containment scoping)."""
    incident = await _incident_container(db, run, args)
    starts = [incident.attacker_ip] if incident.attacker_ip else [incident.host]
    result = await blast_radius(incident.id, [s for s in starts if s], db=db)
    return {"content": json.dumps(result, default=str), **result}


async def _incident_container(db: AsyncSession, run, args: dict) -> ShieldIncident:
    incident = await db.get(ShieldIncident, int(args.get("incident_id", 0)))
    if incident is None or incident.tenant_id != run.tenant_id:
        raise ValueError("incident not found for this tenant")
    return incident


async def _correlate(db: AsyncSession, run, args: dict) -> dict:
    incident = await _incident_container(db, run, args)
    now = time.time()
    window_start = now - 180
    events = (
        (
            await db.execute(
                select(SecurityEvent)
                .where(SecurityEvent.tenant_id == run.tenant_id,
                       SecurityEvent.host == incident.host,
                       SecurityEvent.ts >= dt.datetime.fromtimestamp(window_start, dt.timezone.utc))
                .order_by(SecurityEvent.id)
            )
        )
        .scalars()
        .all()
    )
    raw = [
        {"event": e.event, "user": e.user, "src_ip": e.src_ip, "dst_ip": e.dst_ip,
         "dst_port": e.dst_port, "process": (e.process or "")[:80], "bytes_out": e.bytes_out}
        for e in events
    ]

    techniques = incident.techniques or []
    rule_hits = incident.rule_hits or []
    facts = {
        "host": incident.host, "attacker_ip": incident.attacker_ip,
        "rule_hits": rule_hits, "techniques": techniques, "events": raw[:25],
    }

    narrative = None
    try:
        from app.sentinel.llm import complete

        out = await complete(
            db, run.tenant_id,
            [{"role": "user", "content":
                f"You are SHIELD, a senior SOC analyst. Write a tight incident narrative "
                f"(max 6 sentences) from these verified facts, referencing the MITRE techniques:\n"
                f"{json.dumps(facts, default=str)}\nNarrative:"}],
            origin_module="shield", run_id=run.id,
        )
        narrative = out["content"].strip()
    except Exception:  # noqa: BLE001 — fallback assembles facts, never invents
        pass

    if not narrative:
        lines = []
        for hit in rule_hits:
            lines.append(f"Rule '{hit['rule_name']}' fired: {hit.get('detail', '')}.")
        if incident.attacker_ip:
            lines.append(f"Originating source: {incident.attacker_ip} (blocked on approval).")
        lines.append("Techniques observed: " + ", ".join(
            f"{t['id']} {t['name']} [{t['tactic']}]" for t in techniques))
        narrative = " ".join(lines)

    incident.narrative = narrative
    await db.commit()
    return {"content": json.dumps({"narrative": narrative, "techniques": techniques,
                                   "rule_hits": rule_hits, "host": incident.host}, default=str),
            "techniques": techniques}


async def _graph(db: AsyncSession, run, args: dict) -> dict:
    incident = await _incident_container(db, run, args)
    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    if incident.attacker_ip:
        nodes[incident.attacker_ip] = {"kind": "attacker", "label": incident.attacker_ip}
    nodes[incident.host] = {"kind": "host", "label": incident.host}

    if incident.attacker_ip:
        edges.append({"src": incident.attacker_ip, "dst": incident.host,
                      "label": "attacked", "technique_id": (incident.techniques[0]["id"]
                                                            if incident.techniques else None)})
    for hit in incident.rule_hits or []:
        user = hit.get("user")
        if user:
            nodes[user] = {"kind": "user", "label": user}
            edges.append({"src": user, "dst": incident.host, "label": "logged_in",
                          "technique_id": hit.get("technique_id")})
        if hit.get("dst_ip"):
            nodes[hit["dst_ip"]] = {"kind": "external", "label": hit["dst_ip"]}
            label = "beaconed" if "beacon" in hit["rule_name"].lower() else (
                "exfiltrated" if "exfil" in hit["rule_name"].lower() else "connected")
            edges.append({"src": incident.host, "dst": hit["dst_ip"], "label": label,
                          "technique_id": hit.get("technique_id")})

    node_list = [{"kind": v["kind"], "label": v["label"]} for v in nodes.values()]
    backend = await save_graph(incident.id, node_list, edges, db=db)
    starts = [incident.attacker_ip] if incident.attacker_ip else [incident.host]
    radius = await blast_radius(incident.id, [s for s in starts if s], edges=edges, db=db)
    incident.attack_graph = {"nodes": node_list, "edges": edges, "backend": backend,
                             "blast_radius": radius}
    await db.commit()
    return {"content": json.dumps(incident.attack_graph, default=str), "backend": backend,
            "nodes": len(node_list), "edges": len(edges), "blast_radius": radius}


async def _contain(db: AsyncSession, run, args: dict) -> dict:
    incident = await _incident_container(db, run, args)
    from app.shield import lab

    recommendation: dict = {}
    if incident.attacker_ip and not incident.attacker_ip.startswith("10."):
        recommendation["block_ip"] = incident.attacker_ip
    compromised_user = next((h.get("user") for h in incident.rule_hits or [] if h.get("user")), None)
    if compromised_user:
        recommendation["lock_user"] = compromised_user
    if not recommendation:
        recommendation["isolate_host"] = incident.host

    applied = lab.apply_containment(
        block_ip=recommendation.get("block_ip"),
        lock_user=recommendation.get("lock_user"),
    )
    incident.status = "contained"
    incident.containment = {"recommended": recommendation, "applied": applied}
    await db.commit()
    return {"content": json.dumps({"status": "contained", "recommendation": recommendation,
                                   "applied": applied}, default=str), "contained": True}