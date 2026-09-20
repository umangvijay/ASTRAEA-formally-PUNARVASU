"""Realtime pub/sub bus. Topics: run:{id}, sentinel:{tenant_id}, loom:{tenant_id}.

SSE endpoints subscribe; the engine and the sentinel proxy publish. Persisted events
are replayed from the DB first — the bus only carries the live tail.

Two transports, one contract:
- sqlite / single process: the in-process queues below (what the lab runs on).
- postgres: every publish ALSO fires pg_notify on the shared channel and a
  dedicated listener connection re-dispatches remote events into this process's
  queues — so SSE clients get live push no matter which instance executed the run.
  No new infrastructure: Cloud SQL IS the fan-out broker.

Postgres NOTIFY payloads cap at 8000 bytes. Larger events fan out as a compact
envelope ({kind, run_id, ts, truncated}) — the client learns history moved and
replays it from the DB, which is always authoritative.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections import defaultdict

logger = logging.getLogger("bus")

CHANNEL = "astraea_bus"
_NOTIFY_PAYLOAD_LIMIT = 7000  # headroom under postgres's 8000-byte cap
_INSTANCE_ID = uuid.uuid4().hex[:12]
_listener_task: asyncio.Task | None = None
_listener_stop: asyncio.Event | None = None

_subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)


def subscribe(topic: str) -> asyncio.Queue:
    queue: asyncio.Queue = asyncio.Queue(maxsize=500)
    _subscribers[topic].add(queue)
    return queue


def unsubscribe(topic: str, queue: asyncio.Queue) -> None:
    _subscribers[topic].discard(queue)
    if not _subscribers[topic]:
        _subscribers.pop(topic, None)


def _local_dispatch(topic: str, payload: str) -> None:
    for queue in tuple(_subscribers.get(topic, ())):
        try:
            queue.put_nowait(payload)
        except asyncio.QueueFull:
            pass  # slow consumer drops the live tail; history is in the DB


async def publish(topic: str, event: dict) -> None:
    payload = json.dumps(event, default=str)
    _local_dispatch(topic, payload)
    await _fanout(topic, event, payload)


# ── cross-instance fan-out (postgres only) ─────────────────────────────────
def _is_postgres() -> bool:
    from app.config import settings

    return settings.db_url.startswith(("postgresql+psycopg", "postgresql+asyncpg", "postgresql://"))


def compact_event(event: dict) -> dict:
    """Oversized events fan out as this envelope; the DB replay fills the gap."""
    keep = ("kind", "run_id", "tenant_id", "ts", "id")
    small = {k: event[k] for k in keep if k in event}
    small["truncated"] = True
    return small


async def _fanout(topic: str, event: dict, payload: str) -> None:
    if _listener_stop is None or not _is_postgres():
        return  # single-process mode (sqlite, tests, or fan-out not started)
    body = payload
    if len(body) > _NOTIFY_PAYLOAD_LIMIT:
        body = json.dumps(compact_event(event), default=str)
    envelope = json.dumps({"o": _INSTANCE_ID, "t": topic, "e": body}, default=str)
    if len(envelope) > 8000:
        return  # cannot happen after compaction; guard anyway, never raise the caller
    try:
        from app.db import engine
        from sqlalchemy import text

        async with engine.connect() as conn:
            await conn.execute(
                text("SELECT pg_notify(:ch, :payload)"), {"ch": CHANNEL, "payload": envelope}
            )
            await conn.commit()
    except Exception:  # noqa: BLE001 — fan-out is best-effort; the DB replay covers misses
        logger.warning("bus fan-out failed (local dispatch already delivered)", exc_info=True)


def _dispatch_remote(envelope_raw: str) -> None:
    try:
        envelope = json.loads(envelope_raw)
    except json.JSONDecodeError:
        return
    if envelope.get("o") == _INSTANCE_ID:
        return  # our own notification echoed back — already dispatched locally
    _local_dispatch(envelope.get("t", ""), envelope.get("e", ""))


async def _listener_loop(stop: asyncio.Event) -> None:
    """Hold one dedicated connection on LISTEN astraea_bus; re-dispatch remote
    events into the local queues. Reconnects with backoff — a dropped Cloud SQL
    connection must never take the API down with it."""
    from app.db import engine

    while not stop.is_set():
        try:
            async with engine.connect() as conn:
                raw = (await conn.get_raw_connection()).driver_connection
                raw.autocommit = True
                cursor = await raw.execute(f"LISTEN {CHANNEL}")
                await cursor.close()
                logger.info("bus: LISTEN %s active (instance %s)", CHANNEL, _INSTANCE_ID)
                while not stop.is_set():
                    notification = await raw.notifies.get()
                    if stop.is_set():
                        break
                    _dispatch_remote(notification.payload)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — transient DB loss; retry forever
            logger.warning("bus: listener connection lost — retrying in 2s", exc_info=True)
            try:
                await asyncio.wait_for(stop.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                continue


def start_shared() -> bool:
    """Start cross-instance fan-out when the DB can carry it (postgres).
    Returns whether the shared mode is active. Idempotent."""
    global _listener_task, _listener_stop
    if not _is_postgres():
        return False
    if _listener_task is not None and not _listener_task.done():
        return True
    _listener_stop = asyncio.Event()
    _listener_task = asyncio.get_running_loop().create_task(_listener_loop(_listener_stop))
    return True


async def stop_shared() -> None:
    global _listener_task, _listener_stop
    if _listener_stop is not None:
        _listener_stop.set()
    if _listener_task is not None:
        _listener_task.cancel()
        try:
            await _listener_task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001 — shutdown best-effort
            pass
    _listener_task, _listener_stop = None, None


def sse_format(payload: str | dict) -> str:
    if not isinstance(payload, str):
        payload = json.dumps(payload, default=str)
    return f"data: {payload}\n\n"
