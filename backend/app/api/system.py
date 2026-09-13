"""System endpoints: health, readiness, module registry, workspace mode, platform self-test."""

from __future__ import annotations

import asyncio
import datetime as dt

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import desc, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.modules import MODULES, CORE_SERVICES
from app.shared.deps import get_current_user, get_db

router = APIRouter(tags=["system"])


@router.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "app": settings.app_name.lower(),
        "version": settings.version,
        "mode": "postgres" if settings.db_url.startswith("postgresql") else "sqlite",
        "profile": settings.active_profile,
        "phase": settings.phase,
    }


@router.get("/ready")
async def ready(db: AsyncSession = Depends(get_db)) -> dict:
    await db.execute(text("SELECT 1"))
    return {"status": "ready"}


@router.get("/api/workspace")
async def get_workspace(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """SOLO/FUSION state for this tenant. Memory (LOOM) is shared regardless."""
    from app.shared import workspace as ws

    state = await ws.active_modules(db, user.tenant_id)
    mode = "fusion" if all(state.values()) else "solo"
    solo_module = next((m for m, a in state.items() if a), None) if mode == "solo" else None
    return {"mode": mode, "solo_module": solo_module, "modules": state}


class WorkspaceIn(BaseModel):
    mode: str = Field(pattern="^(fusion|solo)$")
    module: str | None = None


@router.put("/api/workspace")
async def put_workspace(payload: WorkspaceIn, user=Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    from app.shared import workspace as ws

    state = await ws.set_mode(db, user.tenant_id, payload.mode, payload.module)
    return {"mode": payload.mode, "solo_module": payload.module if payload.mode == "solo" else None,
            "modules": state}


@router.get("/api/modules")
async def modules() -> dict:
    return {
        "modules": [
            {**m, "status": f"phase-{m['phase']}"} for m in MODULES
        ],
        "core_services": [{**s, "status": f"phase-{s['phase']}"} for s in CORE_SERVICES],
        "active_profile": settings.active_profile,
        "mode": "postgres" if settings.db_url.startswith("postgresql") else "sqlite",
        "version": settings.version,
        "phase": settings.phase,
    }


async def _alive(task) -> bool:
    return task is not None and not task.done()


@router.get("/api/system/selftest")
async def selftest(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    """Smoke paths across the platform, per module — the watchdog's public face."""
    from app.core.tools import _shell
    from app.forge import jobs as forge_jobs
    from app.pulse import detector as pulse_detector
    from app.shield import detector as shield_detector

    checks: dict[str, dict] = {}

    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = {"ok": True, "detail": settings.db_url.split("://")[0]}
    except Exception as exc:  # noqa: BLE001
        checks["database"] = {"ok": False, "detail": str(exc)[:120]}

    checks["pulse_detector"] = {"ok": await _alive(pulse_detector._loop_task),
                                "detail": f"{settings.detector_interval_seconds}s heartbeat"}
    checks["shield_detector"] = {"ok": await _alive(shield_detector._loop_task),
                                 "detail": f"{settings.shield_detector_interval_seconds}s heartbeat"}
    checks["forge_consolidator"] = {"ok": await _alive(forge_jobs._task), "detail": "nightly"}

    fresh = False
    try:
        from app.pulse.models import MetricPoint

        row = (
            await db.execute(
                select(MetricPoint.ts).order_by(desc(MetricPoint.id)).limit(1)
            )
        ).first()
        if row and row[0]:
            ts = row[0] if row[0].tzinfo else row[0].replace(tzinfo=dt.timezone.utc)
            fresh = (dt.datetime.now(dt.timezone.utc) - ts).total_seconds() < 60
        checks["telemetry_stream"] = {"ok": fresh,
                                      "detail": "live points within 60s" if fresh
                                      else "no points yet — start demo services (profile sre/all)"}
    except Exception as exc:  # noqa: BLE001
        checks["telemetry_stream"] = {"ok": False, "detail": str(exc)[:120]}

    try:
        from app.sentinel.upstream import pick_provider

        provider, model = pick_provider(None)
        general = provider not in ("model_forge", "mlx_local")
        checks["llm_provider"] = {
            "ok": general,
            "detail": f"{provider}/{model}" if general else
            f"{provider}/{model} is SQL/on-device only — set Vertex, Gemini, Groq, or Ollama",
        }
    except Exception as exc:  # noqa: BLE001
        checks["llm_provider"] = {"ok": False, "detail": str(exc)[:160]}

    try:
        result = await asyncio.wait_for(_shell({"command": "echo ok", "timeout": 3}), timeout=5)
        checks["tool_sandbox"] = {"ok": bool(result.get("ok")), "detail": "shell echo"}
    except Exception as exc:  # noqa: BLE001
        checks["tool_sandbox"] = {"ok": False, "detail": str(exc)[:120]}

    degraded = [name for name, c in checks.items() if not c["ok"]]
    return {
        "status": "healthy" if not degraded else "degraded",
        "degraded": degraded,
        "checks": checks,
        "version": settings.version,
    }


# ── Benchmark endpoints ────────────────────────────────────────────────────

@router.get("/api/benchmarks/{module}")
async def get_benchmarks(
    module: str,
    metric: str | None = None,
    limit: int = 100,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get benchmark time series for a module. Optionally filter by metric name."""
    from app.shared.benchmarks import get_series, get_summary

    if metric:
        series = await get_series(db, module, metric, tenant_id=user.tenant_id, limit=limit)
        return {"module": module, "metric": metric, "series": series}

    summary = await get_summary(db, module, tenant_id=user.tenant_id)
    return {"module": module, "summary": summary}


@router.get("/api/benchmarks/{module}/summary")
async def get_benchmark_summary(
    module: str,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get aggregated benchmark stats for all metrics of a module."""
    from app.shared.benchmarks import get_summary

    summary = await get_summary(db, module, tenant_id=user.tenant_id)
    return {"module": module, "summary": summary}

