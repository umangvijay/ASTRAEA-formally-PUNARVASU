"""Milestone 4 gate: OTLP → store → MEDIC queryable telemetry; SHIELD blast radius.

Runs against the sqlite telemetry store + Postgres-fallback graph (the same code paths
ClickHouse/Neo4j use when configured), so the behaviour is verified without external
services in CI.
"""

from __future__ import annotations

import json

from app.pulse import otlp
from app.pulse.store import get_store
from app.db import SessionLocal
from app.shared.security import decode_access_token


def _tid(auth_headers) -> str:
    return decode_access_token(auth_headers["Authorization"].removeprefix("Bearer "))["tid"]


# ── OTLP parsing (pure) ──────────────────────────────────────────────────────
def test_otlp_parse_logs_and_metrics_and_traces():
    logs = otlp.parse_logs({"resourceLogs": [{
        "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "checkout"}}]},
        "scopeLogs": [{"logRecords": [
            {"severityText": "ERROR", "body": {"stringValue": "pool exhausted"}}]}]}]})
    assert logs == [("checkout", "ERROR", "pool exhausted")]

    metrics = otlp.parse_metrics({"resourceMetrics": [{
        "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "payments"}}]},
        "scopeMetrics": [{"metrics": [
            {"name": "error_rate", "gauge": {"dataPoints": [{"asDouble": 0.42}]}},
            {"name": "p95_latency", "gauge": {"dataPoints": [{"asDouble": 900}]}},
            {"name": "ignored_metric", "gauge": {"dataPoints": [{"asDouble": 1}]}}]}]}]})
    assert len(metrics) == 1
    service, cols = metrics[0]
    assert service == "payments"
    assert cols["error_rate"] == 0.42 and cols["p95_latency"] == 900.0
    assert cols["cpu"] == 0.0 and cols["request_rate"] == 0.0  # unfilled columns default

    traces = otlp.parse_traces({"resourceSpans": [{
        "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "inventory"}}]},
        "scopeSpans": [{"spans": [
            {"name": "GET /cart", "status": {"code": 2},
             "startTimeUnixNano": "1000000", "endTimeUnixNano": "6000000"}]}]}]})
    assert traces[0][0] == "inventory" and traces[0][1] == "ERROR"
    assert "GET /cart" in traces[0][2] and "5.0ms" in traces[0][2]


# ── OTLP ingest endpoints → store ────────────────────────────────────────────
async def test_otlp_logs_endpoint_persists(client, auth_headers):
    body = {"resourceLogs": [{
        "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "checkout"}}]},
        "scopeLogs": [{"logRecords": [
            {"severityText": "ERROR", "body": {"stringValue": "db pool exhausted"}}]}]}]}
    resp = await client.post("/api/pulse/v1/logs", headers=auth_headers, json=body)
    assert resp.status_code == 200 and resp.json()["accepted"] == 1

    async with SessionLocal() as db:
        logs = await get_store(db).logs(_tid(auth_headers), "checkout", limit=5)
    assert any("db pool exhausted" in row["message"] for row in logs)


async def test_otlp_metrics_endpoint_feeds_series(client, auth_headers):
    body = {"resourceMetrics": [{
        "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "payments"}}]},
        "scopeMetrics": [{"metrics": [
            {"name": "error_rate", "gauge": {"dataPoints": [{"asDouble": 0.9}]}},
            {"name": "cpu", "gauge": {"dataPoints": [{"asDouble": 55}]}}]}]}]}
    resp = await client.post("/api/pulse/v1/metrics", headers=auth_headers, json=body)
    assert resp.status_code == 200 and resp.json()["accepted"] == 1

    series = (await client.get("/api/pulse/series/payments", headers=auth_headers)).json()
    assert series["points"] and series["points"][-1]["error_rate"] == 0.9


# ── MEDIC queryable telemetry tool ───────────────────────────────────────────
async def test_medic_telemetry_tool_ranks_services(auth_headers):
    tid = _tid(auth_headers)
    from app.medic.tools import _telemetry

    class _Run:
        tenant_id = tid
        origin_module = "medic"
        id = "run-telemetry-test"

    async with SessionLocal() as db:
        store = get_store(db)
        for _ in range(3):
            await store.add_point(tid, "checkout",
                                  {"request_rate": 10, "error_rate": 0.8, "p95_latency": 500, "cpu": 30})
            await store.add_point(tid, "payments",
                                  {"request_rate": 10, "error_rate": 0.1, "p95_latency": 200, "cpu": 20})
        out = await _telemetry(db, _Run(), {"metric": "error_rate", "limit": 5})

    ranked = json.loads(out["content"])["ranked"]
    assert ranked[0]["service"] == "checkout"  # highest avg error_rate ranks first
    assert ranked[0]["avg"] >= ranked[-1]["avg"]


# ── SHIELD blast radius ──────────────────────────────────────────────────────
async def test_shield_blast_radius_over_graph(auth_headers):
    tid = _tid(auth_headers)
    from app.shield.graph import blast_radius, save_graph

    nodes = [{"kind": "attacker", "label": "10.0.1.99"},
             {"kind": "host", "label": "db-1"},
             {"kind": "external", "label": "8.8.8.8"}]
    edges = [{"src": "10.0.1.99", "dst": "db-1", "label": "attacked", "technique_id": "T1110"},
             {"src": "db-1", "dst": "8.8.8.8", "label": "exfiltrated", "technique_id": "T1048"}]

    async with SessionLocal() as db:
        # save_graph needs a real incident id; create a minimal incident row
        from app.shield.models import ShieldIncident

        inc = ShieldIncident(tenant_id=tid, host="db-1", attacker_ip="10.0.1.99")
        db.add(inc)
        await db.commit()
        await db.refresh(inc)
        backend = await save_graph(inc.id, nodes, edges, db=db)
        assert backend == "postgres"  # no neo4j configured in tests
        radius = await blast_radius(inc.id, ["10.0.1.99"], db=db)

    assert radius["backend"] == "postgres"
    assert set(radius["reachable"]) == {"db-1", "8.8.8.8"}
    assert radius["count"] == 2
