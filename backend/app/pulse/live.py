"""Live platform telemetry — this process measuring itself.

MEDIC's Isolation Forest trains on these series. Chaos distorts the same
numbers (a real SLO fault on the control plane), so Cloud Run does not need
the checkout/payments demo services.
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
import resource
import threading
import time
from collections import deque

from app.config import settings
from app.db import SessionLocal

logger = logging.getLogger("pulse.live")

_lock = threading.Lock()
_latencies: deque[float] = deque(maxlen=240)
_statuses: deque[int] = deque(maxlen=240)
_chaos: dict | None = None
_loop_task: asyncio.Task | None = None

KINDS = ("error_storm", "latency_spike", "memory_leak", "dependency_failure", "config_drift")
SERVICE = "astraea-api"


def record_request(duration_ms: float, status: int) -> None:
    with _lock:
        _latencies.append(float(duration_ms))
        _statuses.append(int(status))


def inject_chaos(kind: str | None = None, seconds: int | None = None) -> dict:
    """Distort the live series. MEDIC sees a real drift against this process's baseline."""
    chosen = kind if kind in KINDS else random.choice(KINDS)
    hold = int(seconds or settings.chaos_auto_recover_seconds)
    with _lock:
        global _chaos
        _chaos = {"kind": chosen, "until": time.time() + hold, "service": SERVICE}
    return {"service": SERVICE, "fault": chosen, "auto_recover_s": hold}


def snapshot() -> dict[str, float]:
    with _lock:
        lats = list(_latencies)
        stats = list(_statuses)
        chaos = _chaos if _chaos and _chaos["until"] > time.time() else None
    n = len(lats)
    if n:
        ordered = sorted(lats)
        p95 = float(ordered[min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))])
        err = 100.0 * sum(1 for s in stats if s >= 400) / max(len(stats), 1)
        rate = float(n)
    else:
        p95, err, rate = 40.0, 0.0, 1.0
    try:
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        rss_mb = rss / 1024.0 if os.uname().sysname == "Linux" else rss / (1024.0 * 1024.0)
        cpu = min(99.0, max(2.0, rss_mb / 6.0))
    except Exception:
        cpu = 8.0
    try:
        cpu = min(99.0, max(cpu, os.getloadavg()[0] * 18.0))
    except OSError:
        pass
    metrics = {
        "request_rate": rate,
        "error_rate": err,
        "p95_latency": p95,
        "cpu": cpu,
    }
    if chaos:
        kind = chaos["kind"]
        if kind == "error_storm":
            metrics["error_rate"] = max(metrics["error_rate"], 42.0)
        elif kind == "latency_spike":
            metrics["p95_latency"] = max(metrics["p95_latency"], 920.0)
        elif kind == "memory_leak":
            metrics["cpu"] = max(metrics["cpu"], 88.0)
            metrics["request_rate"] = max(1.0, metrics["request_rate"] * 0.4)
        elif kind == "dependency_failure":
            metrics["error_rate"] = max(metrics["error_rate"], 28.0)
            metrics["p95_latency"] = max(metrics["p95_latency"], 420.0)
        elif kind == "config_drift":
            metrics["error_rate"] = max(metrics["error_rate"], 12.0)
            metrics["p95_latency"] = max(metrics["p95_latency"], 510.0)
    return metrics


async def emit_once() -> None:
    from sqlalchemy import select

    from app.core.models import Tenant
    from app.pulse.store import get_store
    from app.shared.workspace import module_active

    metrics = snapshot()
    async with SessionLocal() as db:
        tenants = (await db.execute(select(Tenant.id).order_by(Tenant.created_at.desc()).limit(80))).scalars().all()
        store = get_store(db)
        for tid in tenants:
            if not await module_active(db, tid, "medic"):
                continue
            await store.add_point(tid, SERVICE, metrics)


async def loop() -> None:
    while True:
        try:
            await emit_once()
        except Exception:
            logger.exception("live telemetry emit failed")
        await asyncio.sleep(2.0)


def start() -> None:
    global _loop_task
    if _loop_task is None or _loop_task.done():
        _loop_task = asyncio.get_running_loop().create_task(loop())
        logger.info("live platform telemetry on (service=%s)", SERVICE)
