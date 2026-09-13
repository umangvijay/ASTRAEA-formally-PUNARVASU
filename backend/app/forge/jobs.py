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
            from app.forge import eval as forge_eval

            async with SessionLocal() as db:
                mining = await forge_eval.mine_failures(db)
                if not mining["proposals"]:
                    continue
                top = mining["proposals"][0]
                candidate = await forge_eval.propose_candidate(
                    db, source="failure-mining", kind="prompt-variant",
                    reason=f"{top['cluster']} ×{top['occurrences']}: {top['change']['suggestion']}",
                    payload={"prompt_template": None},
                )
                eval_run = await forge_eval.run_eval(
                    db, variant_kind="prompt-variant",
                    payload={"prompt_template": None},
                    variant_name=f"consolidator-{candidate.id}",
                )
                verdict = await forge_eval.promote_if_better(
                    db, eval_run=eval_run, candidate=candidate, kind="prompt-variant",
                    payload={"prompt_template": None},
                )
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
