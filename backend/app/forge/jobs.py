"""FORGE's sleep-time compute: the consolidator mines failures nightly, proposes a
candidate, evaluates it on the verifiable suite and promotes only on measured improvement."""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger("forge.jobs")

_task: asyncio.Task | None = None


async def _nightly() -> None:
    from app.config import settings

    interval = settings.forge_consolidator_interval_s
    while True:
        await asyncio.sleep(interval)
        try:
            from app.db import SessionLocal

            async with SessionLocal() as db:
                from app.forge import eval as forge_eval

                verdict = await forge_eval.consolidate_once(db)
            if verdict:
                logger.info("consolidator: %s", json.dumps(verdict, default=str))
        except Exception:  # noqa: BLE001 — sleep-time compute must never crash the platform
            logger.exception("forge consolidator failed")


import json  # noqa: E402


def start() -> None:
    global _task
    if _task is None or _task.done():
        _task = asyncio.get_running_loop().create_task(_nightly())


def stop() -> None:
    global _task
    if _task:
        _task.cancel()
        _task = None
