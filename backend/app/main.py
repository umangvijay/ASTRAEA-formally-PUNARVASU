"""Astraea FastAPI application.

Every module heartbeat runs on every boot — SOLO vs FUSION is an infrastructure
choice (which compose services exist), never a reason to leave agents idle.
A watchdog self-heal loop keeps the heartbeats alive, resets stuck runs and
expires guest workspaces.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, runs, system, tenants
from app.api.vault import router as vault_router
from app.config import settings
from app.db import SessionLocal, init_db
from app.loom.api import router as loom_router
from app.pulse.api import router as pulse_router
from app.shield.api import router as shield_router
from app.api.public import router as public_router
from app.api.fusion import router as fusion_router
from app.forge.api import router as forge_router
from app.vaani.api import router as vaani_router
from app.operator.api import router as operator_router
from app.sentinel.api import router as sentinel_api
from app.sentinel.proxy import router as sentinel_proxy

# ── Structured logging ──────────────────────────────────────────────────────
from app.shared.logging_config import configure_logging
configure_logging()

logger = logging.getLogger("astraea")


async def _start_heartbeats() -> None:
    """Idempotent — safe to call on boot AND from the watchdog after a crash."""
    from app.pulse import detector
    from app.forge import jobs as forge_jobs
    from app.shield import detector as shield_detector
    from app.shield import lab as shield_lab

    detector.start()
    forge_jobs.start()
    shield_detector.start()
    from app.pulse import live as pulse_live
    from app.config import on_cloud_run

    if "pytest" not in sys.modules:
        pulse_live.start()
        from app.shared import retention

        retention.start()
    lab_flag = os.environ.get("ASTRAEA_SHIELD_LAB", "").lower()
    want_lab = lab_flag in ("1", "true", "yes") or (
        not on_cloud_run() and not settings.is_production and lab_flag not in ("0", "false", "no")
    )
    if want_lab:
        if getattr(shield_lab, "_benign_task", None) is None or shield_lab._benign_task.done():
            shield_lab._benign_task = asyncio.get_running_loop().create_task(shield_lab.benign_loop())
    logger.info(
        "heartbeats on: pulse(%ss) shield(%ss) forge(%ss) live-telemetry retention(%ss) lab=%s",
        settings.detector_interval_seconds,
        settings.shield_detector_interval_seconds,
        settings.forge_consolidator_interval_s,
        max(300, settings.retention_interval_seconds),
        want_lab,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.config import apply_production_guards, on_cloud_run

    apply_production_guards()
    app.state.ready = False
    app.state.boot_error = None
    worker_stop = asyncio.Event()
    worker_tasks: list[asyncio.Task] = []
    heal_task: asyncio.Task | None = None

    async def _boot() -> None:
        nonlocal worker_tasks, heal_task
        await init_db()
        from app.core.engine import recover_orphans
        from app.shared.seed import seed, seed_shield, dedupe_guardrail_overrides

        async with SessionLocal() as db:
            await seed(db)
            await seed_shield(db)
            await dedupe_guardrail_overrides(db)
        orphaned = await recover_orphans()
        if orphaned:
            logger.warning("recovery: %d interrupted run(s) awaiting resume", orphaned)

        from app.config import settings as _cfg

        if _cfg.clickhouse_url:
            try:
                from app.pulse.store import ClickHouseTelemetryStore

                async with SessionLocal() as db:
                    await ClickHouseTelemetryStore(db).ensure_tables()
                logger.info("clickhouse telemetry store ready at %s", _cfg.clickhouse_url)
            except Exception:  # noqa: BLE001 — falls back to the sqlite store if CH is down
                logger.warning("clickhouse ensure_tables failed — telemetry uses sqlite store",
                               exc_info=True)

        async def _vector_backfill():
            try:
                from sqlalchemy import select as _sel

                from app.loom.models import LoomItem
                from app.shared import vector

                async with SessionLocal() as db:
                    items = (
                        (await db.execute(
                            _sel(LoomItem).order_by(LoomItem.id.desc()).limit(300)
                        ))
                        .scalars()
                        .all()
                    )
                    for item in items:
                        text = (f"{item.title}\n{item.summary}\n"
                                f"{json.dumps(item.payload or {}, default=str)[:2000]}")
                        await vector.aindex_item(
                            item.id, item.tenant_id, text,
                            {"origin_module": item.origin_module, "kind": item.kind,
                             "title": item.title[:200],
                             "share_with": ",".join(item.share_with or [])},
                        )
                logger.info("vector memory: backfilled %d loom items (%s embeddings)",
                            len(items), vector.embed_kind())
            except Exception:  # noqa: BLE001 — vector memory is best-effort
                logger.exception("vector backfill failed")

        asyncio.get_running_loop().create_task(_vector_backfill())

        # Warm the lazy ML models off the request path: the ONNX injection
        # classifier and the MiniLM embedder otherwise load inside the first
        # run's steps and add seconds to the very first user interaction.
        async def _warm_models():
            try:
                from app.sentinel import onnx_classifier

                await asyncio.get_running_loop().run_in_executor(
                    None, onnx_classifier._ensure_model)
                from app.shared import vector

                await asyncio.get_running_loop().run_in_executor(
                    None, vector.get_embedder)
                logger.info("model warmup: sentinel classifier + vector embedder ready (%s)",
                            vector.embed_kind())
            except Exception:  # noqa: BLE001 — warmup is best-effort; fallbacks exist
                logger.warning("model warmup skipped", exc_info=True)

        asyncio.get_running_loop().create_task(_warm_models())

        await _start_heartbeats()

        from app.config import settings as _settings
        from app.core.worker import run_worker

        worker_tasks = [
            asyncio.get_running_loop().create_task(run_worker(worker_stop))
            for _ in range(max(1, _settings.run_workers))
        ]
        logger.info("started %d durable run worker(s)", len(worker_tasks))

        # Postgres: cross-instance SSE fan-out via LISTEN/NOTIFY (see shared/bus.py).
        # sqlite stays single-process by design — the lab path needs no broker.
        from app.shared import bus as shared_bus

        if shared_bus.start_shared():
            logger.info("bus: shared fan-out active (postgres LISTEN/NOTIFY)")

        async def self_heal():
            """Every 30s: restart dead heartbeats, reset stuck runs, expire old guests."""
            tick = 0
            while True:
                await asyncio.sleep(30)
                tick += 1
                try:
                    await _start_heartbeats()

                    from sqlalchemy import update

                    from app.core.models import Run

                    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=5)
                    async with SessionLocal() as db:
                        result = await db.execute(
                            update(Run).where(
                                Run.status == "running",
                                Run.updated_at < cutoff,
                            ).values(status="interrupted")
                        )
                        if result.rowcount:
                            await db.commit()
                            logger.warning("self-heal: %d stuck run(s) → interrupted", result.rowcount)

                    if tick % 20 == 0:
                        from sqlalchemy import delete, select

                        from app.core.models import Run as _Run, Tenant, User

                        stale = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)
                        # Guests whose runs are all terminal still hold a tenant row
                        # forever if nothing reaps them — give them a longer grace,
                        # then reap too. Guests with live (queued/running/parked) runs
                        # are always kept and counted so the accumulation is visible.
                        stale_hard = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=24)
                        active_statuses = ("queued", "running", "awaiting_approval")
                        async with SessionLocal() as db:
                            guests = (
                                await db.execute(
                                    select(User).where(
                                        User.role == "guest",
                                        User.expires_at.is_not(None),
                                        User.expires_at < stale,
                                    )
                                )
                            ).scalars().all()
                            removed = 0
                            skipped_active = 0
                            skipped_terminal = 0
                            for g in guests:
                                tid = g.tenant_id
                                has_live_run = (await db.execute(
                                    select(_Run.id).where(
                                        _Run.tenant_id == tid, _Run.status.in_(active_statuses)
                                    ).limit(1)
                                )).first()
                                if has_live_run:
                                    skipped_active += 1
                                    continue
                                has_any_run = (await db.execute(
                                    select(_Run.id).where(_Run.tenant_id == tid).limit(1)
                                )).first()
                                if has_any_run:
                                    exp = g.expires_at
                                    if exp is not None and exp.tzinfo is None:
                                        exp = exp.replace(tzinfo=dt.timezone.utc)
                                    if exp is None or exp >= stale_hard:
                                        skipped_terminal += 1
                                        continue
                                await db.execute(delete(User).where(User.id == g.id))
                                await db.execute(delete(Tenant).where(Tenant.id == tid))
                                removed += 1
                            if removed or skipped_active or skipped_terminal:
                                await db.commit()
                                logger.info(
                                    "self-heal: removed %d expired guest workspace(s); "
                                    "kept %d with live run(s), %d terminal awaiting hard grace",
                                    removed, skipped_active, skipped_terminal,
                                )
                        from app.api.auth import _cleanup_old_attempts

                        async with SessionLocal() as db:
                            pruned = await _cleanup_old_attempts(db)
                        if pruned:
                            logger.info("self-heal: pruned %d old login-attempt row(s)", pruned)
                except Exception:  # noqa: BLE001 — self-heal must never crash
                    logger.exception("self-heal tick failed")

        heal_task = asyncio.get_running_loop().create_task(self_heal())
        app.state.ready = True
        logger.info("astraea ready (cloud_run=%s vertex=%s)", on_cloud_run(), bool(settings.vertex_project))

    try:
        if on_cloud_run():
            # Bind PORT immediately so Cloud Run does not 500 while sqlite/seed run.
            asyncio.get_running_loop().create_task(_boot())
        else:
            await _boot()
    except Exception as exc:
        app.state.boot_error = str(exc)
        logger.exception("boot failed")
        if not on_cloud_run():
            raise

    yield
    if heal_task:
        heal_task.cancel()
    worker_stop.set()
    for t in worker_tasks:
        t.cancel()
    from app.pulse import detector
    from app.shared import bus as shared_bus

    detector.stop()
    await shared_bus.stop_shared()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Astraea",
        version=settings.version,
        description=(
            "Control plane for autonomous agents — SOLO modules, FUSION workspace, "
            "one shared brain (LOOM), every LLM call through SENTINEL."
        ),
        lifespan=lifespan,
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None if settings.is_production else "/redoc",
        openapi_url=None if settings.is_production else "/openapi.json",
    )
    from starlette.middleware.base import BaseHTTPMiddleware

    class SecurityHeaders(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            resp = await call_next(request)
            resp.headers["X-Content-Type-Options"] = "nosniff"
            resp.headers["X-Frame-Options"] = "DENY"
            resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
            resp.headers["Permissions-Policy"] = "geolocation=(), microphone=(self), camera=()"
            resp.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
                "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
                "font-src 'self' data:; "
                "connect-src 'self' http://localhost:* http://127.0.0.1:* "
                "https://*.run.app https://*.googleapis.com wss://*.run.app "
                "ws://localhost:* ws://127.0.0.1:*; frame-ancestors 'none'; base-uri 'self'"
            )
            if settings.is_production:
                resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
            return resp

    import time as _time

    class RequestTimingMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            t0 = _time.perf_counter()
            resp = await call_next(request)
            duration_ms = round((_time.perf_counter() - t0) * 1000, 2)
            resp.headers["X-Request-Time"] = f"{duration_ms}ms"
            try:
                from app.pulse import live as pulse_live

                pulse_live.record_request(duration_ms, resp.status_code)
            except Exception:
                pass
            if not request.url.path.startswith("/_next"):
                logger.info(
                    "%s %s → %d (%.1fms)",
                    request.method, request.url.path, resp.status_code, duration_ms,
                    extra={"method": request.method, "path": request.url.path,
                           "status_code": resp.status_code, "duration_ms": duration_ms},
                )
            return resp

    app.add_middleware(RequestTimingMiddleware)

    app.add_middleware(SecurityHeaders)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_list,
        allow_origin_regex=settings.cors_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(system.router)
    app.include_router(auth.router)
    app.include_router(tenants.router)
    app.include_router(runs.router)
    app.include_router(sentinel_proxy)
    app.include_router(sentinel_api)
    app.include_router(loom_router)
    app.include_router(pulse_router)
    app.include_router(operator_router)
    app.include_router(shield_router)
    app.include_router(vaani_router)
    app.include_router(forge_router)
    app.include_router(vault_router)
    app.include_router(fusion_router)
    app.include_router(public_router)
    from app.vaani.gateway import router as vaani_ws
    app.include_router(vaani_ws)
    return app


app = create_app()
