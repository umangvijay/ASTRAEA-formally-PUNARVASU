"""Attack-graph store: Neo4j over HTTP when configured, Postgres tables otherwise.

Both backends persist the same shape — nodes (attacker/host/user/external) and labelled
edges (attacked/logged_in/scanned/beaconed/exfiltrated) with technique annotations.
"""

from __future__ import annotations

import logging

from app.config import settings

logger = logging.getLogger("shield.graph")


async def _neo4j_query(cypher: str, params: dict | None = None,
                       client=None) -> list[dict] | None:
    url = settings.neo4j_url
    if not url:
        return None
    import httpx

    stmt = {"statements": [{"statement": cypher, "parameters": params or {}}]}
    own = client is None
    try:
        if own:
            client = httpx.AsyncClient(timeout=10)
        resp = await client.post(f"{url}/db/neo4j/tx/commit", json=stmt,
                                 headers={"X-Stream": "true"})
        if resp.status_code != 200:
            return None
        data = resp.json()
        rows = data["results"][0].get("data", [])
        return [r["row"] for r in rows]
    except (httpx.HTTPError, KeyError, IndexError, ValueError):
        return None
    finally:
        if own:
            await client.aclose()


async def save_graph(incident_id: int, nodes: list[dict], edges: list[dict], db=None) -> str:
    """Persist to Neo4j when configured (with MERGE idempotency); Postgres is the fallback.

    Neo4j statements share one connection. If ANY statement fails, the whole
    graph goes to Postgres — never a split graph half in Neo4j, half in SQL."""
    if settings.neo4j_url and nodes and edges:
        import httpx

        ok = True
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                for n in nodes:
                    ok &= (await _neo4j_query(
                        "MERGE (x:IncidentNode {incident_id: $iid, label: $label}) "
                        "SET x.kind = $kind",
                        {"iid": incident_id, "label": n["label"], "kind": n["kind"]},
                        client=client,
                    )) is not None
                for e in edges:
                    ok &= (await _neo4j_query(
                        "MATCH (a:IncidentNode), (b:IncidentNode) "
                        "WHERE a.incident_id = $iid AND a.label = $src AND b.incident_id = $iid AND b.label = $dst "
                        "MERGE (a)-[r:ACTION {label: $label}]->(b) SET r.technique_id = $tech",
                        {"iid": incident_id, "src": e["src"], "dst": e["dst"],
                         "label": e["label"], "tech": e.get("technique_id")},
                        client=client,
                    )) is not None
        except httpx.HTTPError:
            ok = False
        if ok:
            return "neo4j"
        logger.warning("shield.graph: neo4j write incomplete for incident %s — "
                       "falling back to the SQL graph in full", incident_id)

    from app.shield.models import ShieldGraphEdge, ShieldGraphNode

    if db is None:
        logger.error("shield.graph: no SQL session available — graph for incident "
                     "%s could not be persisted", incident_id)
        return "unavailable"
    for n in nodes:
        db.add(ShieldGraphNode(incident_id=incident_id, kind=n["kind"], label=n["label"]))
    for e in edges:
        db.add(ShieldGraphEdge(incident_id=incident_id, src=e["src"], dst=e["dst"],
                               label=e["label"], technique_id=e.get("technique_id")))
    await db.commit()
    return "postgres"


async def blast_radius(incident_id: int, start_labels: list[str], *,
                       edges: list[dict] | None = None, db=None) -> dict:
    """Everything reachable from the attack's entry point(s) — the blast radius.

    Uses a Neo4j variable-length Cypher traversal when configured; otherwise a BFS
    over the persisted Postgres edges (works identically in lite mode / tests)."""
    if settings.neo4j_url:
        rows = await _neo4j_query(
            "MATCH (a:IncidentNode {incident_id:$iid})-[*1..6]->(b:IncidentNode {incident_id:$iid}) "
            "WHERE a.label IN $starts RETURN DISTINCT b.label AS label",
            {"iid": incident_id, "starts": start_labels},
        )
        if rows is not None:
            reached = sorted({r[0] for r in rows if r})
            return {"backend": "neo4j", "start": start_labels,
                    "reachable": reached, "count": len(reached)}

    if edges is None and db is not None:
        from sqlalchemy import select

        from app.shield.models import ShieldGraphEdge

        rows = (await db.execute(
            select(ShieldGraphEdge).where(ShieldGraphEdge.incident_id == incident_id)
        )).scalars().all()
        edges = [{"src": e.src, "dst": e.dst, "label": e.label} for e in rows]

    adjacency: dict[str, list[str]] = {}
    for e in edges or []:
        adjacency.setdefault(e["src"], []).append(e["dst"])

    seen: set[str] = set()
    frontier = list(start_labels)
    while frontier:
        node = frontier.pop()
        for nxt in adjacency.get(node, []):
            if nxt not in seen:
                seen.add(nxt)
                frontier.append(nxt)
    return {"backend": "postgres", "start": start_labels,
            "reachable": sorted(seen), "count": len(seen)}
