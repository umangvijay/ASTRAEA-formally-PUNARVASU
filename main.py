#!/usr/bin/env python3
"""
ASTRAEA — one-command launcher.

    python3 main.py                          # full platform (docker infra when available)
    python3 main.py --profile sre            # SOLO: only MEDIC's extra infrastructure
    python3 main.py --no-frontend            # API only
    python3 main.py --check                  # environment report only
    python3 main.py --down                   # stop docker infra

Phases (docs/MASTER_SPEC.md):
    0 skeleton · 1 core+sentinel+loom · 2 medic · 3 operator · 4 shield
    5 vaani · 6 forge+model-forge · 7 hardening
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import signal
import subprocess
import sys
import threading
import time
import urllib.request
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND_PORT = int(os.environ.get("ASTRAEA_BACKEND_PORT") or os.environ.get("PUNARVASU_BACKEND_PORT") or "8000")
FRONTEND_PORT = int(os.environ.get("ASTRAEA_FRONTEND_PORT") or os.environ.get("PUNARVASU_FRONTEND_PORT") or "3000")

SHUTDOWN = threading.Event()

# profile → compose profiles to activate
COMPOSE_PROFILES = {
    "core": ["core"],
    "sre": ["core", "sre"],
    "soc": ["core", "soc"],
    "voice": ["core"],
    "operator": ["core"],
    "forge": ["core"],
    "all": ["core", "sre", "soc", "observability"],
}

FREE_KEYS = [
    ("GEMINI_API_KEY", "https://aistudio.google.com/apikey", "streaming LLM · vision · tool calls"),
    ("GROQ_API_KEY", "https://console.groq.com/keys", "instant Llama + Whisper STT"),
    ("HF_TOKEN", "https://huggingface.co/settings/tokens", "ONNX guardrails · OmniParser"),
]


def c(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m"


def banner() -> None:
    print(c("╔════════════════════════════════════════════════════╗", "2"))
    print(c("║  A S T R A E A — control plane for agents          ║", "1"))
    print(c("╚════════════════════════════════════════════════════╝", "2"))


# ────────────────────────── environment ──────────────────────────
def load_dotenv() -> dict[str, str]:
    """Minimal .env parser (no extra deps)."""
    values: dict[str, str] = {}
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            values[key.strip()] = val.strip()
    return values


def report_keys(env: dict[str, str]) -> None:
    print(c("── free-tier model keys ─────────────────────────────", "2"))
    for name, url, use in FREE_KEYS:
        if env.get(name):
            print(f"  {c('●', '32')} {name:<16} set      {use}")
        else:
            print(f"  {c('○', '33')} {name:<16} missing  {use}")
            print(f"      get it free: {url}")
    print(c("  Phase 0 runs with all keys missing — they matter from Phase 1.", "2"))


def venv_python() -> Path:
    return ROOT / ".venv" / "bin" / "python"


def ensure_venv() -> None:
    if venv_python().exists():
        return
    print(c("── first run: creating virtualenv + installing backend deps ──", "2"))
    subprocess.run([sys.executable, "-m", "venv", str(ROOT / ".venv")], check=True)
    subprocess.run(
        [str(venv_python()), "-m", "pip", "install", "--quiet", "--upgrade", "pip"],
        check=True,
    )
    proc = subprocess.run(
        [str(venv_python()), "-m", "pip", "install", "-r", str(ROOT / "backend" / "requirements.txt")]
    )
    if proc.returncode != 0:
        print(c("pip install failed — see output above.", "31"))
        sys.exit(1)


def ensure_node_modules() -> None:
    if (ROOT / "frontend" / "node_modules").exists() or not shutil_which("npm"):
        return
    print(c("── first run: installing frontend deps (npm) ──", "2"))
    subprocess.run(["npm", "install"], cwd=ROOT / "frontend", check=True)


def shutil_which(cmd: str) -> str | None:
    from shutil import which

    return which(cmd)


def docker_available() -> bool:
    docker = shutil_which("docker")
    if not docker:
        return False
    if subprocess.run(["docker", "info", "--format", "ok"], capture_output=True).returncode != 0:
        return False
    # compose plugin may be missing (homebrew docker CLI ships without it)
    return subprocess.run(["docker", "compose", "version"], capture_output=True).returncode == 0


def port_busy(port: int) -> bool:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def resolve_port(requested: int, what: str) -> int:
    """If another app owns the port, shift upward instead of crashing mid-boot."""
    port = requested
    while port_busy(port):
        port += 1
    if port != requested:
        print(c(f"  ⚠ port {requested} busy ({what}) → using {port}", "33"))
    return port


def compose_up(profile: str, env: dict[str, str]) -> str:
    """Returns the DB URL the backend should use."""
    profiles = COMPOSE_PROFILES.get(profile)
    if not docker_available() or profiles is None:
        print(c("── docker not available → single-node storage (sqlite, no containers) ──", "33"))
        return env.get("ASTRAEA_DATABASE_URL", env.get("PUNARVASU_DATABASE_URL", ""))

    args: list[str] = ["docker", "compose", "-f", str(ROOT / "docker-compose.yml")]
    for p in profiles:
        args += ["--profile", p]
    args += ["up", "-d", "--wait", "--wait-timeout", "180"]
    print(c(f"── docker mode: starting infra ({', '.join(profiles)}) ──", "2"))
    proc = subprocess.run(args)
    if proc.returncode != 0:
        print(c("docker compose failed → falling back to single-node storage.", "33"))
        return env.get("ASTRAEA_DATABASE_URL", env.get("PUNARVASU_DATABASE_URL", ""))
    return (env.get("ASTRAEA_DATABASE_URL") or env.get("PUNARVASU_DATABASE_URL")
            or "postgresql+psycopg://astra:astra@localhost:5432/punarvasu")


def _ingest_token(env: dict[str, str]) -> str:
    """Demo services authenticate with the internal pipeline token (dev default: dev-internal)."""
    return (env.get("ASTRAEA_INGEST_TOKEN") or env.get("PUNARVASU_INGEST_TOKEN")
            or ("dev-internal" if env.get("ASTRAEA_ENV", env.get("PUNARVASU_ENV", "dev")) != "production" else ""))


def run_migrations(env: dict[str, str]) -> None:
    child_env = os.environ.copy()
    child_env.update(env)
    child_env["PYTHONPATH"] = str(ROOT / "backend")
    proc = subprocess.run(
        [str(venv_python()), "-m", "alembic", "upgrade", "head"],
        cwd=ROOT / "backend",
        env=child_env,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        print(c("alembic upgrade head failed:", "31"))
        print(proc.stdout[-1500:])
        print(proc.stderr[-1500:])
        sys.exit(1)
    print(c("── migrations: ok ──", "2"))


# ────────────────────────── process manager ──────────────────────────
class ManagedProcess:
    def __init__(self, name: str, cmd: list[str], cwd: Path, env: dict[str, str], color: str) -> None:
        self.name = name
        self.color = color
        self.ring: deque[str] = deque(maxlen=200)
        full_env = os.environ.copy()
        full_env.update(env)
        self.proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=full_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        self.thread = threading.Thread(target=self._pump, daemon=True)
        self.thread.start()

    def _pump(self) -> None:
        assert self.proc.stdout is not None
        for line in self.proc.stdout:
            line = line.rstrip()
            self.ring.append(line)
            if not SHUTDOWN.is_set():
                print(f"{c(f'[{self.name}]', self.color)} {line}")

    def wait(self) -> int | None:
        return self.proc.wait()

    def terminate(self) -> None:
        try:
            os.killpg(os.getpgid(self.proc.pid), signal.SIGTERM)
        except ProcessLookupError:
            pass

    def dump_tail(self) -> None:
        print(c(f"── last lines from [{self.name}] ──", "31"))
        for line in list(self.ring)[-50:]:
            print(f"  {line}")


_NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def http_ok(url: str, timeout: float = 2.0) -> bool:
    """True only if OUR api answers — avoids false positives from other apps on the same port.

    Uses a proxy-free opener: env HTTP_PROXY must never hijack 127.0.0.1 health
    checks (that made the status line report api:DOWN while uvicorn served fine).
    """
    try:
        with _NO_PROXY_OPENER.open(url, timeout=timeout) as resp:
            if resp.status != 200:
                return False
            if "/health" in url:
                import json

                return json.load(resp).get("app") == "astraea"
            return True
    except Exception:
        return False


def status_line(api: bool, web: bool, mode: str, profile: str, started: float) -> None:
    up = lambda flag: c("UP", "32") if flag else c("DOWN", "31")
    elapsed = time.strftime("%H:%M:%S", time.gmtime(time.time() - started))
    line = (
        f"  ASTRAEA ▸ api:{up(api)} ▸ console:{up(web)} ▸ storage:{mode} "
        f"▸ profile:{profile} ▸ uptime:{elapsed}   (Ctrl-C to stop)"
    )
    print("\x1b[2K\r" + line, end="", flush=True)


def wait_health(processes: dict[str, ManagedProcess], mode: str) -> tuple[bool, bool]:
    api = http_ok(f"http://127.0.0.1:{BACKEND_PORT}/health")
    web = http_ok(f"http://127.0.0.1:{FRONTEND_PORT}")
    deadline = time.time() + 120
    while time.time() < deadline and not SHUTDOWN.is_set():
        api = http_ok(f"http://127.0.0.1:{BACKEND_PORT}/health")
        web = "frontend" not in processes or http_ok(f"http://127.0.0.1:{FRONTEND_PORT}")
        if api and web:
            break
        time.sleep(1.5)
    return api, web


# ────────────────────────── main ──────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="Punarvasu launcher")
    parser.add_argument("--profile", default="all", choices=list(COMPOSE_PROFILES) + ["lite"])
    parser.add_argument("--no-frontend", action="store_true")
    parser.add_argument("--no-infra", action="store_true", help="skip docker even if available")
    parser.add_argument("--check", action="store_true", help="environment report only")
    parser.add_argument("--down", action="store_true", help="stop docker infra and exit")
    args = parser.parse_args()

    banner()
    env = load_dotenv()

    if args.down:
        if docker_available():
            subprocess.run(["docker", "compose", "-f", str(ROOT / "docker-compose.yml"), "down"])
        print("infra stopped.")
        return

    report_keys(env)

    if args.check:
        print(c("── toolchain ────────────────────────────────────────", "2"))
        for name, ver in [("python", sys.version.split()[0])]:
            print(f"  ● {name}: {ver}")
        for cmd in ["node", "npm", "docker"]:
            path = shutil_which(cmd)
            print(f"  {'●' if path else '○'} {cmd}: {'found' if path else 'MISSING'}")
        if venv_python().exists():
            print("  ● backend venv: ready")
        else:
            print("  ○ backend venv: will be created on first run")
        print(c("── done ──", "2"))
        return

    ensure_venv()
    ensure_node_modules()

    # coexist with other apps on this machine (e.g. 8000/3000 taken by a running AgentOS)
    global BACKEND_PORT, FRONTEND_PORT
    BACKEND_PORT = resolve_port(BACKEND_PORT, "api default port")
    FRONTEND_PORT = resolve_port(FRONTEND_PORT, "console default port")

    # decide mode + database url
    profile = args.profile
    mode = "sqlite"
    db_url = env.get("ASTRAEA_DATABASE_URL", env.get("PUNARVASU_DATABASE_URL", ""))
    if not args.no_infra and profile in COMPOSE_PROFILES:
        db_url = compose_up(profile, env)
        if "postgresql" in db_url:
            mode = "postgres"
    else:
        print(c(f"── single-node storage (sqlite) · profile={profile} ──", "33"))

    if db_url.startswith("sqlite"):
        (ROOT / "data").mkdir(exist_ok=True)

    child_env = {
        "ASTRAEA_DATABASE_URL": db_url,
        "ASTRAEA_ACTIVE_PROFILE": profile,
        "ASTRAEA_MODE": mode,
    }
    # dev convenience: never boot without a jwt secret (warned in report)
    if not env.get("ASTRAEA_JWT_SECRET") and not env.get("PUNARVASU_JWT_SECRET"):
        child_env["ASTRAEA_JWT_SECRET"] = "dev-" + secrets.token_hex(16)

    run_migrations({**env, **child_env})

    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "data" / "runtime.json").write_text(json.dumps({
        "api_port": BACKEND_PORT, "frontend_port": FRONTEND_PORT,
        "mode": mode, "profile": profile,
        "api_public_url": env.get("ASTRAEA_PUBLIC_API_URL", ""),
    }))
    print(c("── starting services ──", "2"))
    processes: dict[str, ManagedProcess] = {}
    if profile in ("sre", "all"):
        processes["demo"] = ManagedProcess(
            "demo",
            [str(venv_python()), "-m", "app.demo.services"],
            cwd=ROOT / "backend",
            env={**child_env,
                 "PYTHONPATH": str(ROOT / "backend"),
                 "ASTRAEA_INGEST_URL": f"http://127.0.0.1:{BACKEND_PORT}/api/pulse/ingest",
                 "ASTRAEA_INGEST_TOKEN": _ingest_token(env)},
            color="33",
        )
    api_env = {
        **child_env,
        "PYTHONPATH": str(ROOT / "backend"),
        "PUNARVASU_BACKEND_PORT": str(BACKEND_PORT),
    }
    processes["api"] = ManagedProcess(
        "api",
        [str(venv_python()), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
         "--port", str(BACKEND_PORT)],
        cwd=ROOT / "backend",
        env=api_env,
        color="36",
    )
    if not args.no_frontend:
        processes["frontend"] = ManagedProcess(
            "console",
            ["npm", "run", "dev"],
            cwd=ROOT / "frontend",
            env={**child_env, "PORT": str(FRONTEND_PORT)},
            color="35",
        )

    def watch(name: str, proc: ManagedProcess) -> None:
        code = proc.wait()
        if code is None or SHUTDOWN.is_set():
            return
        print(f"\n{c(f'[{name}] exited with code {code}', '31')}")
        proc.dump_tail()
        # Demo bind collisions and a crashed Next must not take the API down.
        if name == "api":
            if http_ok(f"http://127.0.0.1:{BACKEND_PORT}/health"):
                # The process we spawned died but something still serves the API
                # on our port — it was replaced externally. Killing the console
                # and demo for that would be wrong; keep watching instead.
                print(c("  api process was replaced but /health still answers — "
                        "keeping the platform up.", "33"))
                return
            # sys.exit in this daemon thread would NOT stop the launcher — the
            # main loop would keep printing api:DOWN forever. graceful_shutdown
            # interrupts the main thread when exit_after is set.
            graceful_shutdown(processes, exit_after=True)

    for name, proc in processes.items():
        threading.Thread(target=watch, args=(name, proc), daemon=True).start()

    started = time.time()
    api_up, web_up = wait_health(processes, mode)
    print()
    if api_up:
        print(c(f"  ✔ api      http://127.0.0.1:{BACKEND_PORT}/health", "32"))
    else:
        print(c("  ✖ api did not become healthy in time", "31"))
    if "frontend" in processes:
        if web_up:
            print(c(f"  ✔ console  http://127.0.0.1:{FRONTEND_PORT}", "32"))
        else:
            print(c("  ✖ console did not become healthy in time", "31"))
    print(c("  docs: docs/RUNBOOK.md · spec: docs/MASTER_SPEC.md", "2"))
    print()

    try:
        while True:
            status_line(api_up, web_up, mode, profile, started)
            api_up = http_ok(f"http://127.0.0.1:{BACKEND_PORT}/health")
            web_up = "frontend" not in processes or http_ok(f"http://127.0.0.1:{FRONTEND_PORT}")
            time.sleep(3)
    except KeyboardInterrupt:
        print("\n" + c("── shutting down ──", "2"))
        graceful_shutdown(processes)


def graceful_shutdown(processes: dict[str, ManagedProcess], exit_after: bool = False) -> None:
    if SHUTDOWN.is_set():
        return
    SHUTDOWN.set()
    for proc in reversed(list(processes.values())):
        proc.terminate()
    deadline = time.time() + 6
    for proc in reversed(list(processes.values())):
        while proc.proc.poll() is None and time.time() < deadline:
            time.sleep(0.2)
        if proc.proc.poll() is None:
            try:
                os.killpg(os.getpgid(proc.proc.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
    if exit_after:
        # The caller may be a daemon thread, where sys.exit() would not stop the
        # process — interrupt the main loop so the launcher actually exits.
        os.kill(os.getpid(), signal.SIGINT)


if __name__ == "__main__":
    main()
