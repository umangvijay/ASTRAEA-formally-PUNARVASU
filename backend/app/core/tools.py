"""Tool registry — real tools, sandboxed. Phase 1 ships three:

- shell:     subprocess with CPU/filesize/NPROC rlimits + timeout (docker microVM lands in Phase 3+)
- http_get:  SSRF-guarded fetch (https, no private ranges, size-capped)
- loom_read: pulls this module's stamped context from LOOM

Every call is recorded as a run event; unknown tools raise, they never silently no-op.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from urllib.parse import urlparse

import httpx

from app.config import settings

logger = logging.getLogger("core.tools")

BLOCKED_HOSTS = ("localhost", "127.", "0.0.0.0", "10.", "192.168.", "172.16.", "169.254.", "[::1]")
_host_fallback_warned = False


async def run_tool(db, run, name: str, args: dict) -> dict:
    if name == "shell":
        return await _shell(args)
    if name == "http_get":
        return await _http_get(args)
    if name == "loom_read":
        from app.loom.service import context_for

        items = await context_for(db, run.tenant_id, run.origin_module, limit=20)
        return {"ok": True, "output": json.dumps(items, default=str)[:4000]}
    if name == "operator.run_task":
        from app.operator.runner import run_task as operator_run_task

        result = await operator_run_task(db, run, args)
        return {"ok": bool(result.get("success")), "output": str(result.get("content", "")), **result}
    if name == "vaani.book":
        try:
            booking = json.loads(args.get("booking_json", "{}"))
        except json.JSONDecodeError as exc:
            # a malformed booking must read as a validation error, not a raw traceback
            raise ValueError(f"booking_json is not valid JSON: {exc}")
        if not isinstance(booking, dict):
            raise ValueError("booking_json must be a JSON object")
        from app.vaani.brain import book as vaani_book

        result = await vaani_book(db, run.tenant_id, booking, origin_run_id=run.id)
        return {"ok": True, "output": json.dumps(result, default=str), **result}
    if name.startswith("shield."):
        from app.shield.tools import dispatch as shield_dispatch

        result = await shield_dispatch(db, run, name, args)
        return {"ok": True, "output": str(result.get("content", "")), **result}
    if name.startswith("medic."):
        from app.medic.tools import dispatch as medic_dispatch

        result = await medic_dispatch(db, run, name, args)
        return {"ok": True, "output": str(result.get("content", "")), **result}
    if name in ("web.search", "web.fetch", "web.research", "web.scrape"):
        from app.operator import web as webmod

        if name == "web.search":
            hits = await webmod.search(str(args.get("query", "")),
                                       max_results=int(args.get("max_results", 5)))
            return {"ok": True, "output": json.dumps(hits, default=str), "hits": hits}
        if name == "web.fetch":
            page = await webmod.fetch_url(str(args.get("url", "")))
            return {"ok": page.get("ok", False), "output": json.dumps(page, default=str), **page}
        if name == "web.scrape":
            page = await webmod.scrape_url(
                str(args.get("url", "")),
                limit=min(int(args.get("limit", 12_000)), 40_000),
                include_links=bool(args.get("include_links", True)),
            )
            return {"ok": page.get("ok", False), "output": json.dumps(page, default=str), **page}
        pack = await webmod.research(str(args.get("query", "")),
                                     max_results=int(args.get("max_results", 4)))
        return {"ok": True, "output": json.dumps(pack, default=str), **pack}
    raise ValueError(f"unknown tool '{name}'")


def _preexec():  # POSIX child hardening (NPROC excluded — it counts all user procs on macOS)
    import resource

    resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1_000_000, 1_000_000))


async def _shell(args: dict) -> dict:
    command = str(args.get("command", "")).strip()
    if not command:
        raise ValueError("shell tool requires a 'command'")
    timeout = min(float(args.get("timeout", 10)), 30)
    max_output = int(args.get("max_output", 100_000))

    # Milestone 3: prefer a fully isolated container (no network, read-only, capped).
    if settings.sandbox_enabled:
        from app.core import sandbox

        if await sandbox.docker_available_async():
            return await sandbox.run_sandboxed(command, timeout=timeout, max_output=max_output)
        global _host_fallback_warned
        if not _host_fallback_warned:
            logger.warning(
                "sandbox: Docker unavailable — DEGRADED to host rlimit subprocess for "
                "shell tools. Install Docker (and optionally gVisor/runsc) for full isolation.")
            _host_fallback_warned = True

    return await _shell_host(command, timeout, max_output)


async def _shell_host(command: str, timeout: float, max_output: int) -> dict:
    """Degraded fallback: run on the host with POSIX rlimits (no container boundary)."""
    proc = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        preexec_fn=_preexec if sys.platform != "win32" else None,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        # reap the killed child — otherwise every timeout leaks a zombie
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            pass
        return {"ok": False, "output": f"tool timeout after {timeout}s",
                "exit_code": None, "sandbox": "host"}
    return {
        "ok": proc.returncode == 0,
        "output": out.decode(errors="replace").rstrip()[:max_output],
        "exit_code": proc.returncode,
        "sandbox": "host",
    }


async def _http_get(args: dict) -> dict:
    url = str(args.get("url", "")).strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("http_get requires a valid http(s) url")
    # Resolution-based SSRF guard: the hostname must resolve to public
    # addresses only — prefix checks missed 172.17-31, CGNAT, IPv6 ULA and
    # non-dotted hosts (decimal/hex) that resolve into private space.
    from app.shared.ssrf import aassert_public_host

    await aassert_public_host(url)
    timeout = min(float(args.get("timeout", 10)), 20)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        resp = await client.get(url, headers={"User-Agent": "Astraea-Agent/0.2"})
    return {
        "ok": resp.status_code < 400,
        "output": f"HTTP {resp.status_code}\n{resp.text[:200_000]}",
        "status": resp.status_code,
    }
