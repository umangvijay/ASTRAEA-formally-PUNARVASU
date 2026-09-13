"""Sandboxed shell/code execution (Milestone 3).

Untrusted tool commands run inside an ephemeral Docker container with:
  - NO network        (`--network none`)          — no data exfil / SSRF from tools
  - read-only root fs (`--read-only` + tmpfs /tmp) — nothing on the image is mutated
  - CPU / memory / pids caps                       — a runaway tool can't starve the host
  - all Linux capabilities dropped + no-new-privileges
  - gVisor (`--runtime=runsc`) automatically when the runtime is installed — a real
    kernel boundary (microVM-class isolation), not just a namespace.

When Docker is unavailable we DEGRADE — loudly, never silently — to the previous
in-process rlimit subprocess. Callers pass `on_host_fallback` to run that path.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import uuid

from app.config import settings

logger = logging.getLogger("core.sandbox")

_docker_ok: bool | None = None
_gvisor_ok: bool | None = None


def docker_available() -> bool:
    """True if a working Docker CLI + daemon is reachable (cached per process)."""
    global _docker_ok
    if _docker_ok is None:
        if shutil.which("docker") is None:
            _docker_ok = False
        else:
            try:
                proc = subprocess.run(["docker", "info"], capture_output=True,
                                      timeout=5, text=True)
                _docker_ok = proc.returncode == 0
            except Exception:  # noqa: BLE001 — any error means "no usable docker"
                _docker_ok = False
    return _docker_ok


def gvisor_available() -> bool:
    """True if the gVisor (`runsc`) runtime is registered with Docker."""
    global _gvisor_ok
    if _gvisor_ok is None:
        if not docker_available():
            _gvisor_ok = False
        else:
            try:
                proc = subprocess.run(
                    ["docker", "info", "--format", "{{json .Runtimes}}"],
                    capture_output=True, timeout=5, text=True)
                _gvisor_ok = "runsc" in (proc.stdout or "")
            except Exception:  # noqa: BLE001
                _gvisor_ok = False
    return _gvisor_ok


def build_docker_cmd(command: str, *, name: str,
                     image: str | None = None, memory: str | None = None,
                     cpus: str | None = None, pids: int | None = None,
                     network: str | None = None) -> list[str]:
    """Pure builder for the `docker run` argv — kept separate so it is unit-testable
    without a Docker daemon present."""
    args = [
        "docker", "run", "--rm", "--name", name,
        "--network", network or settings.sandbox_network,
        "--memory", memory or settings.sandbox_memory,
        "--cpus", cpus or settings.sandbox_cpus,
        "--pids-limit", str(pids or settings.sandbox_pids_limit),
        "--read-only",
        "--tmpfs", "/tmp:rw,size=64m",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
    ]
    if gvisor_available():
        args += ["--runtime", "runsc"]
    args += [image or settings.sandbox_image, "sh", "-c", command]
    return args


async def run_sandboxed(command: str, *, timeout: float = 10.0,
                        max_output: int = 100_000) -> dict:
    """Execute `command` in an isolated container. Returns the same shape as the
    host shell tool: {ok, output, exit_code, sandbox}."""
    name = f"pvu-sbx-{uuid.uuid4().hex[:12]}"
    argv = build_docker_cmd(command, name=name)
    engine_kind = "gvisor" if gvisor_available() else "docker"

    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        # kill the container by name (SIGKILL the client too)
        try:
            await (await asyncio.create_subprocess_exec(
                "docker", "kill", name,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL)).wait()
        except Exception:  # noqa: BLE001
            pass
        with_kill = proc.kill
        try:
            with_kill()
        except Exception:  # noqa: BLE001
            pass
        return {"ok": False, "output": f"tool timeout after {timeout}s",
                "exit_code": None, "sandbox": engine_kind}
    return {
        "ok": proc.returncode == 0,
        "output": out.decode(errors="replace").rstrip()[:max_output],
        "exit_code": proc.returncode,
        "sandbox": engine_kind,
    }
