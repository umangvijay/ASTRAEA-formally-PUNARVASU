"""Demo microservices: checkout, payments, inventory.

Three real FastAPI services that push live telemetry to PULSE every 2s (OTLP-shaped
payloads over the internal ingest token). They accept chaos faults that change their
actual behaviour (error storms, latency spikes, memory pressure, dependency failures,
config drift) — the telemetry then shows the truth, and config_drift plants a REAL
bug in the service's config.json that MEDIC's patch step must reverse.

Run:  python -m app.demo.services   (spawned by main.py on profiles sre/all)
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import socket
import sys
import time
from contextlib import asynccontextmanager, suppress
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException

from app.config import settings

DATA_DIR = Path(
    os.environ.get("ASTRAEA_DEMO_DATA", str(settings.data_dir / "demo"))
)

DEFAULT_CONFIGS: dict[str, dict] = {
    "checkout": {"pool_size": 20, "timeout_ms": 200, "circuit_breaker": False},
    "payments": {"pool_size": 15, "timeout_ms": 300, "circuit_breaker": False},
    "inventory": {"pool_size": 10, "timeout_ms": 150, "circuit_breaker": False},
}

FAULT_KINDS = ("error_storm", "latency_spike", "memory_leak", "dependency_failure", "config_drift")


def _config_path(service: str) -> Path:
    return DATA_DIR / service / "config.json"


def load_config(service: str) -> dict:
    """Read from disk on every call — so a planted config bug is real and a patch really fixes it.

    A corrupted config file degrades to the planted defaults (with a loud
    warning) instead of 500ing /health and silently killing the telemetry tick."""
    path = _config_path(service)
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            import logging

            logging.getLogger("demo.%s" % service).warning(
                "config file unreadable — serving defaults (%s)", path)
    cfg = dict(DEFAULT_CONFIGS[service])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2))
    return cfg


def write_config(service: str, cfg: dict) -> None:
    path = _config_path(service)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2))


class ServiceState:
    def __init__(self, name: str, port: int):
        self.name = name
        self.port = port
        self.fault: str | None = None
        self.fault_until: float = 0.0
        self.leases_in_use = 0  # config_drift pretends pool exhaustion with this
        self.tenant_id: str | None = None  # tenant that injected the current chaos; owns its telemetry

    def chaos(self, kind: str, seconds: int, tenant_id: str | None = None) -> None:
        if kind not in FAULT_KINDS:
            raise ValueError(f"unknown chaos kind '{kind}'")
        self.fault = kind
        self.fault_until = time.time() + seconds
        if tenant_id:
            self.tenant_id = tenant_id  # telemetry attribution follows the injector
        if kind == "config_drift":
            cfg = load_config(self.name)
            cfg["pool_size"] = 1  # the planted bug — a real file change
            write_config(self.name, cfg)

    def tick(self) -> None:
        if self.fault and time.time() > self.fault_until:
            self.clear()
        # memory_leak keeps growing until recovery
        if self.fault == "memory_leak":
            self.leases_in_use = min(self.leases_in_use + 3, 500)

    def clear(self) -> None:
        self.fault = None
        self.leases_in_use = 0

    def telemetry(self) -> dict[str, float]:
        rate = random.gauss(10, 2)
        error = max(0.0, random.gauss(0.5, 0.4))
        p95 = max(20.0, random.gauss(80, 15))
        cpu = max(5.0, random.gauss(25, 6))
        if self.fault == "error_storm":
            error = random.gauss(40, 6)
        elif self.fault == "latency_spike":
            p95 = random.gauss(900, 80)
        elif self.fault == "memory_leak":
            cpu = min(98.0, cpu + self.leases_in_use)
            rate = max(1.0, rate - self.leases_in_use / 20)
        elif self.fault == "dependency_failure":
            error = random.gauss(25, 5)
            p95 = random.gauss(400, 60)
        elif self.fault == "config_drift":
            cfg = load_config(self.name)
            if cfg["pool_size"] <= 2:  # the bug is live
                p95 = random.gauss(500, 60)
                error = random.gauss(8, 2)
        return {
            "request_rate": round(rate, 2),
            "error_rate": round(max(0.0, error), 2),
            "p95_latency": round(max(20.0, p95), 2),
            "cpu": round(min(100.0, max(0.0, cpu)), 2),
        }


STATES: dict[str, ServiceState] = {}
INGEST = (os.environ.get("ASTRAEA_INGEST_URL")
          or os.environ.get("PUNARVASU_INGEST_URL")
          or "http://127.0.0.1:8000/api/pulse/ingest")
TOKEN = (os.environ.get("ASTRAEA_INGEST_TOKEN")
         or os.environ.get("PUNARVASU_INGEST_TOKEN")
         or "")


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def build_app(service: str, port: int) -> FastAPI:
    state = ServiceState(service, port)
    STATES[service] = state

    async def emit_loop():
        while True:
            try:
                state.tick()
                m = state.telemetry()
                headers = {"X-Internal-Token": TOKEN}
                if state.tenant_id:
                    headers["X-Tenant-Id"] = state.tenant_id
                async with httpx.AsyncClient(timeout=5) as client:
                    await client.post(INGEST, json={
                        "type": "metrics", "service": service, "metrics": m},
                        headers=headers)
                    if random.random() < 0.08:
                        level, msg = "INFO", f"{service}: request batch processed"
                        if state.fault:
                            level = "ERROR"
                            msgs = {
                                "error_storm": f"{service}: 5xx burst — upstream handler panicking",
                                "latency_spike": f"{service}: slow query, p95 breached SLO",
                                "memory_leak": f"{service}: heap climb, leases not released ({state.leases_in_use})",
                                "dependency_failure": f"{service}: dependency timeout calling payments",
                                "config_drift": f"{service}: connection pool exhausted, pool_size too small",
                            }
                            msg = msgs[state.fault]
                        await client.post(INGEST, json={
                            "type": "log", "service": service, "level": level, "message": msg},
                            headers=headers)
            except Exception:
                # emitters never crash the service; PULSE being down is
                # survivable — but a misconfigured INGEST must be visible
                import logging

                logging.getLogger("demo.%s" % service).warning(
                    "telemetry emit failed: %s", sys.exc_info()[1])
            await asyncio.sleep(2)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        load_config(service)  # ensure config file exists
        task = asyncio.create_task(emit_loop())
        try:
            yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    app = FastAPI(title=f"demo-{service}", docs_url=None, redoc_url=None, lifespan=lifespan)

    @app.get("/health")
    async def health():
        cfg = load_config(service)
        return {"service": service, "status": "healthy" if not state.fault else f"fault:{state.fault}",
                "config": cfg}

    @app.get("/diagnose")
    async def diagnose():
        """MEDIC's reproducer probes this: the service reports its own live state honestly."""
        cfg = load_config(service)
        return {"service": service, "mode": state.fault or "healthy",
                "fault_remaining_s": max(0, round(state.fault_until - time.time(), 1)),
                "config": cfg,
                "leases_in_use": state.leases_in_use,
                "telemetry": state.telemetry()}

    @app.post("/chaos/{kind}")
    async def chaos(kind: str, seconds: int = 0, tenant_id: str | None = None):
        state.chaos(kind, seconds or settings.chaos_auto_recover_seconds, tenant_id)
        return {"service": service, "fault": state.fault,
                "auto_recover_s": seconds or settings.chaos_auto_recover_seconds}

    return app


async def inject_chaos(tenant_id: str, service: str | None, kind: str | None) -> dict:
    """Called by PULSE's chaos API — picks randomly when omitted (unscripted faults).
    Talks to the demo services over HTTP: they run in their own process. The caller's
    tenant rides along so the injected fault's telemetry is attributed to them."""
    services = settings.demo_services
    service = service or random.choice(list(services))
    kind = kind or random.choice(FAULT_KINDS)
    if service not in services:
        raise HTTPException(status_code=404, detail=f"unknown demo service '{service}'")
    from urllib.parse import quote as _quote

    result = await _call_service(service, f"/chaos/{kind}?tenant_id={_quote(tenant_id)}")

    # benchmark row + deploy correlation signal
    from app.db import SessionLocal
    from app.pulse.models import FaultInjection
    from app.pulse.store import get_store

    async with SessionLocal() as db:
        db.add(FaultInjection(tenant_id=tenant_id, service=service, kind=kind))
        await db.commit()
        store = get_store(db)
        await store.add_deploy(
            tenant_id, service,
            "config_change" if kind == "config_drift" else "deploy",
            f"chaos:{kind} rolled to {service}"
            + (" — pool_size reduced to 1" if kind == "config_drift" else ""),
        )
    return result


async def _call_service(service: str, path: str) -> dict:
    port = settings.demo_services[service]
    async with httpx.AsyncClient(timeout=5) as client:
        resp = await client.post(f"http://127.0.0.1:{port}{path}")
        resp.raise_for_status()
        return resp.json()


def run_all() -> None:
    apps = []
    for service, port in settings.demo_services.items():
        apps.append((build_app(service, port), port))

    async def serve() -> None:
        async def _one(app, port: int) -> None:
            if not _port_free(port):
                print(f"demo-{port}: already bound — reuse leftover process")
                await asyncio.Event().wait()
                return
            try:
                await uvicorn.Server(
                    uvicorn.Config(app=app, host="127.0.0.1", port=port, log_level="warning")
                ).serve()
            except SystemExit:
                print(f"demo-{port}: port busy — holding")
                await asyncio.Event().wait()
            except OSError as exc:
                print(f"demo-{port}: {exc} — holding")
                await asyncio.Event().wait()

        await asyncio.gather(*(_one(a, p) for a, p in apps))

    asyncio.run(serve())


if __name__ == "__main__":
    run_all()
