"""Benchmark recording and retrieval for all ASTRAEA modules.

Every module records its benchmark metrics after operations:
  - MEDIC: MTTD (ms), MTTR (ms)
  - OPERATOR: task success rate (0-1)
  - SHIELD: detection rate (0-1), false-positive rate (0-1)
  - VAANI: p95 latency (ms)
  - FORGE: eval score (0-1)
  - SENTINEL: scan latency (ms), detection accuracy (0-1)

Data is stored in the `benchmarks` table, queryable by module + metric name + time
range. The API returns time series suitable for charting.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from sqlalchemy import Column, DateTime, Float, Integer, String, Text, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import Base

logger = logging.getLogger("shared.benchmarks")


class Benchmark(Base):
    __tablename__ = "benchmarks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    module = Column(String(32), nullable=False, index=True)
    metric = Column(String(64), nullable=False, index=True)
    value = Column(Float, nullable=False)
    metadata_json = Column(Text, nullable=True)
    tenant_id = Column(String(36), nullable=True, index=True)
    recorded_at = Column(DateTime, default=lambda: dt.datetime.now(dt.timezone.utc), index=True)


async def record(
    db: AsyncSession,
    module: str,
    metric: str,
    value: float,
    *,
    tenant_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> Benchmark:
    """Record a single benchmark measurement."""
    import json

    row = Benchmark(
        module=module,
        metric=metric,
        value=value,
        tenant_id=tenant_id,
        metadata_json=json.dumps(metadata) if metadata else None,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    logger.debug("benchmark: %s.%s = %.4f", module, metric, value)
    return row


async def get_series(
    db: AsyncSession,
    module: str,
    metric: str,
    *,
    tenant_id: str | None = None,
    limit: int = 100,
    since: dt.datetime | None = None,
) -> list[dict]:
    """Retrieve benchmark time series for charting."""
    q = (
        select(Benchmark)
        .where(Benchmark.module == module, Benchmark.metric == metric)
        .order_by(desc(Benchmark.recorded_at))
        .limit(limit)
    )
    if tenant_id:
        q = q.where(Benchmark.tenant_id == tenant_id)
    if since:
        q = q.where(Benchmark.recorded_at >= since)

    rows = (await db.execute(q)).scalars().all()

    import json
    return [
        {
            "value": r.value,
            "recorded_at": r.recorded_at.isoformat() if r.recorded_at else None,
            "metadata": json.loads(r.metadata_json) if r.metadata_json else None,
        }
        for r in reversed(rows)  # oldest first for time series
    ]


async def get_latest(
    db: AsyncSession,
    module: str,
    metric: str,
    *,
    tenant_id: str | None = None,
) -> float | None:
    """Get the most recent benchmark value for a module/metric."""
    q = (
        select(Benchmark.value)
        .where(Benchmark.module == module, Benchmark.metric == metric)
        .order_by(desc(Benchmark.recorded_at))
        .limit(1)
    )
    if tenant_id:
        q = q.where(Benchmark.tenant_id == tenant_id)

    result = (await db.execute(q)).scalar_one_or_none()
    return result


async def get_summary(
    db: AsyncSession,
    module: str,
    *,
    tenant_id: str | None = None,
) -> dict[str, dict]:
    """Get summary stats (latest, avg, min, max, count) for all metrics of a module."""
    q = (
        select(
            Benchmark.metric,
            func.count(Benchmark.id).label("count"),
            func.avg(Benchmark.value).label("avg"),
            func.min(Benchmark.value).label("min"),
            func.max(Benchmark.value).label("max"),
        )
        .where(Benchmark.module == module)
        .group_by(Benchmark.metric)
    )
    if tenant_id:
        q = q.where(Benchmark.tenant_id == tenant_id)

    rows = (await db.execute(q)).all()
    summary = {}
    for row in rows:
        latest = await get_latest(db, module, row.metric, tenant_id=tenant_id)
        summary[row.metric] = {
            "latest": latest,
            "avg": round(float(row.avg), 4) if row.avg else None,
            "min": round(float(row.min), 4) if row.min else None,
            "max": round(float(row.max), 4) if row.max else None,
            "count": row.count,
        }
    return summary
