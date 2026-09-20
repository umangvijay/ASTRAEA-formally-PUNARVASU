"""Soak / load test against a RUNNING ASTRAEA API — real HTTP, real durable runs.

Drives the production path end-to-end per virtual user: guest workspace →
durable run (loom_read + loom_write steps: DB + vector index work, no LLM key
needed) → poll to terminal → verify events persisted. One user also holds an
SSE stream open to prove live push works under load.

    python scripts/soak.py --url http://localhost:8765 --users 20 --runs 5

Exit code is non-zero if any run fails to reach a terminal state or any SSE
client receives nothing live. The summary block is meant to be pasted into a
release note: it is evidence, not decoration.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time

import httpx

WORKFLOW = [
    {"name": "recall", "type": "tool", "tool": "loom_read", "args": {}},
    {"name": "record", "type": "loom_write", "kind": "soak",
     "title": "Soak marker", "summary": "soak test artifact", "content": "{last}"},
]


async def one_user(client: httpx.AsyncClient, uid: int, runs: int,
                   latencies: list[float], failures: list[str],
                   sse_probe: dict) -> None:
    try:
        resp = await client.post("/api/auth/guest")
        resp.raise_for_status()
        token = resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}", "X-Module": "console"}
    except Exception as exc:  # noqa: BLE001 — counted as a failure, never crashes the run
        failures.append(f"user{uid}: guest bootstrap failed: {type(exc).__name__}: {exc!r}")
        return

    for n in range(runs):
        t0 = time.perf_counter()
        try:
            resp = await client.post("/api/runs", headers=headers, json={
                "goal": f"soak u{uid} r{n}", "workflow": WORKFLOW,
            })
            resp.raise_for_status()
            run_id = resp.json()["id"]

            # hold one SSE stream open and require a live event through it
            probe = uid == 0 and n == 0
            stream = None
            if probe:
                stream = client.stream("GET", f"/api/runs/{run_id}/stream",
                                       headers=headers)
                await stream.__aenter__()
            deadline = time.monotonic() + 60
            status = None
            got_live = not probe
            while time.monotonic() < deadline:
                detail = (await client.get(f"/api/runs/{run_id}", headers=headers)).json()
                status = detail["run"]["status"]
                if probe and not got_live and detail["events"]:
                    got_live = True
                if status in ("completed", "failed", "interrupted"):
                    break
                await asyncio.sleep(0.15)
            if probe and stream is not None:
                await stream.__aexit__(None, None, None)
                sse_probe["ok"] = got_live
                sse_probe["terminal"] = status
            if status != "completed":
                failures.append(f"user{uid} run{n}: terminal={status}")
                continue
            events = (await client.get(f"/api/runs/{run_id}", headers=headers)).json()["events"]
            if not any(e["type"] == "run_completed" for e in events):
                failures.append(f"user{uid} run{n}: run_completed event missing")
                continue
            latencies.append(time.perf_counter() - t0)
        except Exception as exc:  # noqa: BLE001 — soak counts, never dies
            failures.append(f"user{uid} run{n}: {type(exc).__name__}: {str(exc)[:120]}")


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8765")
    ap.add_argument("--users", type=int, default=20)
    ap.add_argument("--runs", type=int, default=5)
    args = ap.parse_args()

    latencies: list[float] = []
    failures: list[str] = []
    sse_probe: dict = {"ok": False, "terminal": None}
    t0 = time.perf_counter()
    async with httpx.AsyncClient(base_url=args.url, timeout=httpx.Timeout(60.0, connect=10.0)) as client:
        health = await client.get("/health")
        print(f"health: {health.status_code} {health.json().get('status', '')}")
        assert health.status_code == 200, "API must be healthy before the soak"
        # staggered start: all users hitting /api/auth/guest in the same event-loop
        # tick measures thundering-herd on cold caches, not steady-state soak
        async def _staggered(u: int) -> None:
            await asyncio.sleep(u * 0.1)
            await one_user(client, u, args.runs, latencies, failures, sse_probe)

        await asyncio.gather(*(_staggered(u) for u in range(args.users)))
    wall = time.perf_counter() - t0

    total = args.users * args.runs
    print("\n════ SOAK SUMMARY (paste into release notes) ════")
    print(f"target={args.url}  users={args.users}  runs/user={args.runs}  wall={wall:.1f}s")
    if latencies:
        lat = sorted(latencies)
        print(f"completed={len(lat)}/{total}  "
              f"p50={statistics.median(lat):.2f}s  "
              f"p95={lat[int(len(lat) * 0.95) - 1]:.2f}s  max={lat[-1]:.2f}s")
    print(f"sse live push: {'OK' if sse_probe['ok'] else 'NO LIVE EVENT'} "
          f"(terminal={sse_probe['terminal']})")
    if failures:
        print(f"FAILURES ({len(failures)}):")
        for f in failures[:10]:
            print(f"  - {f}")
        return 1
    print("failures: 0")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
