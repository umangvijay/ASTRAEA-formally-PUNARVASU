"""In-process realtime pub/sub bus. Topics: run:{id}, sentinel:{tenant_id}, loom:{tenant_id}.

SSE endpoints subscribe; the engine and the sentinel proxy publish. Persisted events
are replayed from the DB first — the bus only carries the live tail.
"""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict

_subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)


def subscribe(topic: str) -> asyncio.Queue:
    queue: asyncio.Queue = asyncio.Queue(maxsize=500)
    _subscribers[topic].add(queue)
    return queue


def unsubscribe(topic: str, queue: asyncio.Queue) -> None:
    _subscribers[topic].discard(queue)
    if not _subscribers[topic]:
        _subscribers.pop(topic, None)


async def publish(topic: str, event: dict) -> None:
    payload = json.dumps(event, default=str)
    for queue in tuple(_subscribers.get(topic, ())):
        try:
            queue.put_nowait(payload)
        except asyncio.QueueFull:
            pass  # slow consumer drops the live tail; history is in the DB


def sse_format(payload: str) -> str:
    return f"data: {payload}\n\n"
