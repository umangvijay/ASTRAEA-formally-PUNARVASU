"""Record real control-plane security events into SHIELD's event store.

Login failures, successful sessions, SENTINEL blocks and guest admissions are
this tenant's actual audit trail — not alice/bob lab traffic.
"""
from __future__ import annotations

import logging

from app.db import SessionLocal
from app.shield.models import SecurityEvent

logger = logging.getLogger("shield.live")


async def record(
    tenant_id: str | None,
    *,
    event: str,
    host: str = "astraea-api",
    user: str | None = None,
    src_ip: str | None = None,
    process: str | None = None,
    dst_port: int | None = None,
    external: bool = True,
    bytes_out: int = 0,
) -> None:
    if not tenant_id:
        return
    try:
        async with SessionLocal() as db:
            db.add(SecurityEvent(
                tenant_id=tenant_id,
                host=host,
                event=event,
                user=(user or "")[:60] or None,
                src_ip=src_ip,
                dst_port=dst_port,
                external=external,
                process=(process or "")[:2000] or None,
                bytes_out=int(bytes_out),
            ))
            await db.commit()
    except Exception:
        logger.exception("shield live record failed (%s)", event)
