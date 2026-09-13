"""Milestone 3 gate: sandboxed tool execution.

- The container command drops the host: no network, read-only fs, capped resources.
- When Docker is present we prove a tool cannot read a host file or reach the network.
- When Docker is absent we DEGRADE to the host rlimit path — and say so (never silent).
"""

from __future__ import annotations

import pytest

from app.core import sandbox
from app.core import tools


def test_build_docker_cmd_has_isolation_flags():
    argv = sandbox.build_docker_cmd("echo hi", name="pvu-sbx-test")
    joined = " ".join(argv)
    assert "--network none" in joined, "tool container must have no network"
    assert "--read-only" in joined, "tool container root fs must be read-only"
    assert "--memory" in joined and "--cpus" in joined and "--pids-limit" in joined
    assert "--cap-drop ALL" in joined
    assert "no-new-privileges" in joined
    assert argv[-3:] == ["sh", "-c", "echo hi"]


async def test_shell_uses_sandbox_when_docker_available(monkeypatch):
    monkeypatch.setattr(sandbox, "docker_available", lambda: True)
    called = {}

    async def fake_run_sandboxed(command, *, timeout, max_output):
        called["command"] = command
        return {"ok": True, "output": "sandboxed-ok", "exit_code": 0, "sandbox": "docker"}

    monkeypatch.setattr(sandbox, "run_sandboxed", fake_run_sandboxed)
    result = await tools._shell({"command": "echo hello"})
    assert called["command"] == "echo hello"
    assert result["sandbox"] == "docker"
    assert result["output"] == "sandboxed-ok"


async def test_shell_degrades_to_host_when_docker_absent(monkeypatch):
    monkeypatch.setattr(sandbox, "docker_available", lambda: False)
    # reset the "warned once" latch so we can observe that degradation is flagged
    monkeypatch.setattr(tools, "_host_fallback_warned", False)

    result = await tools._shell({"command": "echo host-path-ok"})
    assert result["ok"] and "host-path-ok" in result["output"]
    assert result["sandbox"] == "host"
    # the degradation was recorded (logged once) — never a silent host fallback
    assert tools._host_fallback_warned is True


@pytest.mark.skipif(not sandbox.docker_available(), reason="Docker not available in this env")
async def test_sandbox_blocks_host_file_and_network(tmp_path):
    """Real container: no network egress, and no visibility of a host secret file."""
    secret = tmp_path / "host_secret.txt"
    secret.write_text("TOP-SECRET-HOST-DATA")

    # the host file path does not exist inside the container
    r1 = await sandbox.run_sandboxed(f"cat {secret} 2>&1 || echo NO_HOST_FILE", timeout=20)
    assert "TOP-SECRET-HOST-DATA" not in r1["output"]
    assert "NO_HOST_FILE" in r1["output"]

    # no network: DNS/connect must fail
    r2 = await sandbox.run_sandboxed(
        "wget -q -T 3 -O- http://example.com 2>&1 || echo NO_NETWORK", timeout=20)
    assert "NO_NETWORK" in r2["output"]
