"""SHIELD detector: DB-driven signature rules + Isolation Forest statistical confirmation.

evaluate_rules(events, rules) is a PURE function over a list of security events — the
FP drill and the live tick share the exact same code. Rule thresholds live in the DB
(seeded as data, editable per tenant). The Isolation Forest layer scores each host's
feature window and attaches statistical confidence; rules carry the decision.

On detection: a ShieldIncident is persisted and a durable SHIELD run spawns through
the core engine (correlate → graph → containment gate → postmortem → LOOM).
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
import statistics
import time

import numpy as np
from sqlalchemy import desc, select
from sklearn.ensemble import IsolationForest

from app.config import settings
from app.core import engine
from app.core.models import Run
from app.db import SessionLocal
from app.shield.models import AttackTechnique, SecurityEvent, ShieldIncident, ShieldRule
from app.shared.bus import publish

logger = logging.getLogger("shield.detector")

_loop_task: asyncio.Task | None = None


# ── pure rule evaluation ───────────────────────────────────────────
def evaluate_rules(events: list[dict], rules: list[dict]) -> list[dict]:
    """events: dicts with keys host/event/user/src_ip/dst_ip/dst_port/bytes_out/process/ts.
    rules: dicts with name/event_types/threshold{evaluator,...}/technique_id. Returns hits."""
    hits: list[dict] = []
    for rule in rules:
        if not rule.get("enabled", True):
            continue
        th = rule.get("threshold", {})
        ev_types = set(rule.get("event_types", []))
        window_s = float(th.get("window_s", 60))
        relevant = [e for e in events if e.get("event") in ev_types]
        if not relevant:
            continue
        evaluator = th.get("evaluator")
        hit = None

        if evaluator == "count_per_src":
            by_src: dict[str, int] = {}
            for e in relevant:
                by_src[e.get("src_ip") or "?"] = by_src.get(e.get("src_ip") or "?", 0) + 1
            for src, count in by_src.items():
                if count >= th.get("count", 5) and src != "?":
                    hit = {"src_ip": src, "count": count, "detail": f"{count} {ev_types} events from {src}"}

        elif evaluator == "success_after_failures":
            by_host_src: dict[tuple, list[dict]] = {}
            for e in sorted(relevant, key=lambda x: x.get("ts", 0)):
                by_host_src.setdefault((e["host"], e.get("src_ip")), []).append(e)
            for (host, src), evs in by_host_src.items():
                fails = sum(1 for e in evs if e["event"] == "login_failure")
                success = next((e for e in evs if e["event"] == "login_success"), None)
                if fails >= th.get("failures", 3) and success is not None:
                    hit = {"src_ip": src, "host": host, "user": success.get("user"),
                           "detail": f"successful login from {src} after {fails} failures"}

        elif evaluator == "distinct_dst_ports":
            by_host: dict[str, set] = {}
            for e in relevant:
                if e.get("dst_port"):
                    by_host.setdefault(e["host"], set()).add(e["dst_port"])
            for host, ports in by_host.items():
                if len(ports) >= th.get("ports", 8):
                    hit = {"host": host, "detail": f"scanned {len(ports)} distinct ports in {int(window_s)}s"}

        elif evaluator == "bytes_out":
            by_host: dict[str, int] = {}
            for e in relevant:
                if e.get("external"):
                    by_host[e["host"]] = by_host.get(e["host"], 0) + int(e.get("bytes_out", 0))
            for host, total in by_host.items():
                if total >= th.get("bytes", 4_000_000):
                    hit = {"host": host, "detail": f"{total/1e6:.1f}MB outbound to external in {int(window_s)}s"}

        elif evaluator == "beacon_periodicity":
            by_pair: dict[tuple, list[float]] = {}
            for e in relevant:
                if e.get("dst_ip") and e.get("external"):
                    by_pair.setdefault((e["host"], e["dst_ip"]), []).append(e.get("ts", 0))
            for (host, dst), times in by_pair.items():
                if len(times) >= th.get("count", 4):
                    intervals = [b - a for a, b in zip(times, times[1:])]
                    if intervals and statistics.pstdev(intervals) < th.get("max_jitter_s", 2.0):
                        hit = {"host": host, "dst_ip": dst,
                               "detail": f"{len(times)} fixed-interval beacons to {dst}"}

        elif evaluator == "process_pattern":
            patterns = th.get("patterns", [])
            for e in relevant:
                proc = (e.get("process") or "").lower()
                if any(p.lower() in proc for p in patterns):
                    hit = {"host": e["host"], "user": e.get("user"), "detail": f"suspicious process: {proc[:80]}"}
                    break

        if hit:
            hits.append({"rule_name": rule["name"], "technique_id": rule["technique_id"],
                         "severity": rule.get("severity", "high"), **hit})
    return hits


def if_score(features: list[list[float]], latest: list[float]) -> float | None:
    """Statistical confidence: Isolation Forest decision over the host's own
    event features. Pure function — rules carry the decision, the forest only
    adds corroboration to the evidence. Needs a real history to learn from."""
    if len(features) < 20 or not latest:
        return None
    model = IsolationForest(n_estimators=80, contamination=0.05, random_state=7)
    model.fit(features)
    return float(model.decision_function([latest])[0])


async def _evaluate_tenant(tenant_id: str) -> list[ShieldIncident]:
    async with SessionLocal() as db:
        now = time.time()
        window_start = now - settings.shield_window_seconds
        events = (
            (
                await db.execute(
                    select(SecurityEvent)
                    .where(SecurityEvent.tenant_id == tenant_id,
                           SecurityEvent.ts >= dt.datetime.fromtimestamp(window_start, dt.timezone.utc),
                           SecurityEvent.blocked.is_(False))
                    .order_by(SecurityEvent.ts)
                )
            )
            .scalars()
            .all()
        )
        if not events:
            return []
        plain = [
            {"host": e.host, "event": e.event, "user": e.user, "src_ip": e.src_ip,
             "dst_ip": e.dst_ip, "dst_port": e.dst_port, "external": e.external,
             "process": e.process, "bytes_out": e.bytes_out,
             "ts": e.ts.timestamp() if e.ts.tzinfo else e.ts.replace(tzinfo=dt.timezone.utc).timestamp()}
            for e in events
        ]
        rules = (
            (
                await db.execute(
                    select(ShieldRule).where(
                        ShieldRule.enabled.is_(True),
                        (ShieldRule.tenant_id.is_(None)) | (ShieldRule.tenant_id == tenant_id),
                    )
                )
            )
            .scalars()
            .all()
        )
        rule_dicts = [
            {"name": r.name, "event_types": r.event_types, "threshold": r.threshold,
             "technique_id": r.technique_id, "severity": r.severity, "enabled": r.enabled}
            for r in rules
        ]
        hits = evaluate_rules(plain, rule_dicts)
        if not hits:
            return []

        # Statistical corroboration: Isolation Forest over each hit host's
        # numeric event features (bytes, ports, external flag) — attached as
        # evidence on the hit. Needs ≥20 events to have learned anything.
        host_events: dict[str, list[dict]] = {}
        for e in plain:
            host_events.setdefault(e["host"], []).append(e)
        for hit in hits:
            hit_host = hit.get("host") or next(
                (e["host"] for e in plain if e.get("src_ip") == hit.get("src_ip")), None)
            evs = host_events.get(hit_host or "", [])
            feats = [[float(e.get("bytes_out") or 0), float(e.get("dst_port") or 0),
                      1.0 if e.get("external") else 0.0] for e in evs]
            score = if_score(feats, feats[-1] if feats else [])
            if score is not None:
                hit["if_score"] = round(score, 4)

        # dedupe: one open incident per host per cooldown
        open_incidents = (
            (
                await db.execute(
                    select(ShieldIncident)
                    .where(ShieldIncident.tenant_id == tenant_id,
                           ShieldIncident.status.in_(["open", "containment_pending"]))
                )
            )
            .scalars()
            .all()
        )
        cooldown = dt.timedelta(seconds=settings.shield_incident_cooldown_seconds)
        now_dt = dt.datetime.now(dt.timezone.utc)
        blocked_hosts = set()
        for i in open_incidents:
            detected = i.detected_at
            if detected is not None and detected.tzinfo is None:
                detected = detected.replace(tzinfo=dt.timezone.utc)  # sqlite returns naive UTC
            if detected and (now_dt - detected).total_seconds() < cooldown.total_seconds():
                blocked_hosts.add(i.host)

        incidents: list[ShieldIncident] = []
        spawn_after_commit: list[str] = []
        seen_hosts: set[str] = set()
        for hit in hits:
            host = hit.get("host") or next((e["host"] for e in plain if e.get("src_ip") == hit.get("src_ip")), "unknown")
            if host in blocked_hosts or host in seen_hosts:
                continue
            seen_hosts.add(host)
            techniques = sorted({h["technique_id"] for h in hits if
                                 (h.get("host") or hit.get("host")) == (hit.get("host") or host)
                                 or h.get("src_ip") == hit.get("src_ip")})
            tech_rows = (await db.execute(
                select(AttackTechnique).where(AttackTechnique.id.in_(techniques))
            )).scalars().all()
            tech_out = [{"id": t.id, "name": t.name, "tactic": t.tactic} for t in tech_rows]

            incident = ShieldIncident(
                tenant_id=tenant_id, host=host,
                attacker_ip=hit.get("src_ip") or hit.get("dst_ip"),
                severity=hit.get("severity", "high"),
                rule_hits=hits, techniques=tech_out,
                narrative="",  # correlate step writes it
                status="open",
            )
            db.add(incident)
            await db.flush()
            incidents.append(incident)
            run_id = await _spawn_shield_run(db, incident)
            spawn_after_commit.append(run_id)
        await db.commit()
        # publish only after the incident + run are durable — SSE consumers must
        # never receive an incident id that fails to commit
        for incident in incidents:
            await publish(f"shield:{tenant_id}", {
                "kind": "incident", "incident_id": incident.id, "host": incident.host,
                "techniques": incident.techniques, "severity": incident.severity,
            })
        for spawned in spawn_after_commit:
            engine.spawn(spawned)
        return incidents


async def _spawn_shield_run(db, incident: ShieldIncident) -> str:
    steps = engine.validate_workflow([
        {"name": "correlate", "type": "tool", "tool": "shield.correlate", "args": {"incident_id": incident.id}},
        {"name": "graph", "type": "tool", "tool": "shield.graph", "args": {"incident_id": incident.id}},
        {"name": "gate", "type": "approval",
         "prompt": "Review the SHIELD incident above. Approve the recommended containment."},
        {"name": "contain", "type": "tool", "tool": "shield.contain", "args": {"incident_id": incident.id}},
        {"name": "postmortem", "type": "loom_write", "kind": "incident",
         "title": "SOC incident: {goal}", "summary": "postmortem by SHIELD",
         "content": "{correlate}", "share_with": ["medic", "operator", "forge"]},
    ])
    run = Run(
        tenant_id=incident.tenant_id,
        goal=f"Contain {incident.host} incident ({', '.join(t['id'] for t in incident.techniques)})",
        workflow=steps, origin_module="shield",
    )
    db.add(run)
    await db.flush()
    incident.run_id = run.id
    return run.id


async def detect_once(tenant_id: str) -> list[ShieldIncident]:
    return await _evaluate_tenant(tenant_id)


async def loop() -> None:
    """SHIELD heartbeat — honors the tenant's SOLO/FUSION switch."""
    while True:
        try:
            from app.shared.workspace import module_active

            async with SessionLocal() as db:
                tenants = (await db.execute(
                    select(SecurityEvent.tenant_id).distinct()
                )).scalars().all()
            for tenant_id in tenants:
                async with SessionLocal() as db:
                    if not await module_active(db, tenant_id, "shield"):
                        continue
                # one tenant's failure must not abort the others this tick
                try:
                    await detect_once(tenant_id)
                except Exception:  # noqa: BLE001 — per-tenant isolation
                    logger.exception("shield detect failed for tenant %s", tenant_id)
        except Exception:  # noqa: BLE001 — heartbeat survives anything
            logger.exception("shield tick failed")
        await asyncio.sleep(settings.shield_detector_interval_seconds)


def start() -> None:
    global _loop_task
    if _loop_task is None or _loop_task.done():
        _loop_task = asyncio.get_running_loop().create_task(loop())


def stop() -> None:
    global _loop_task
    if _loop_task:
        _loop_task.cancel()
        _loop_task = None
