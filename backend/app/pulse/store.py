"""Telemetry store: sqlite (lite mode) by default, ClickHouse over HTTP when configured.

Both backends implement the same interface — production path and dev path are real
code paths, never mocks. ClickHouse talks plain HTTP (JSONEachRow / JSON) so we stay
dependency-light.
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

import httpx
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.pulse.models import DeployEvent, LogRecord, MetricPoint

METRIC_COLUMNS = ("request_rate", "error_rate", "p95_latency", "cpu")


class SqliteTelemetryStore:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def add_point(self, tenant_id: str, service: str, m: dict[str, float]) -> None:
        self.db.add(MetricPoint(tenant_id=tenant_id, service=service, **{c: float(m[c]) for c in METRIC_COLUMNS}))
        await self.db.commit()

    async def add_log(self, tenant_id: str, service: str, level: str, message: str) -> None:
        self.db.add(LogRecord(tenant_id=tenant_id, service=service, level=level, message=message))
        await self.db.commit()

    async def add_deploy(self, tenant_id: str, service: str, kind: str, description: str) -> None:
        self.db.add(DeployEvent(tenant_id=tenant_id, service=service, kind=kind, description=description))
        await self.db.commit()

    async def window(self, tenant_id: str, service: str, limit: int = 120) -> list[dict[str, float]]:
        rows = (
            (
                await self.db.execute(
                    select(MetricPoint)
                    .where(MetricPoint.tenant_id == tenant_id, MetricPoint.service == service)
                    .order_by(desc(MetricPoint.id))
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        return [
            {"ts": str(r.ts), **{c: getattr(r, c) for c in METRIC_COLUMNS}} for r in reversed(rows)
        ]

    async def logs(self, tenant_id: str, service: str, limit: int = 20) -> list[dict[str, str]]:
        rows = (
            (
                await self.db.execute(
                    select(LogRecord)
                    .where(LogRecord.tenant_id == tenant_id, LogRecord.service == service)
                    .order_by(desc(LogRecord.id))
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        return [{"level": r.level, "message": r.message, "ts": str(r.ts)} for r in reversed(rows)]

    async def deploys(self, tenant_id: str, service: str, limit: int = 5) -> list[dict[str, str]]:
        rows = (
            (
                await self.db.execute(
                    select(DeployEvent)
                    .where(DeployEvent.tenant_id == tenant_id, DeployEvent.service == service)
                    .order_by(desc(DeployEvent.id))
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        return [{"kind": r.kind, "description": r.description, "ts": str(r.ts)} for r in reversed(rows)]

    async def top_services(self, tenant_id: str, metric: str = "error_rate",
                           limit: int = 5) -> list[dict]:
        """Grouped telemetry query the MEDIC investigator can call — avg/max/count per
        service, ranked by average of the requested metric."""
        metric = metric if metric in METRIC_COLUMNS else "error_rate"
        col = getattr(MetricPoint, metric)
        rows = (await self.db.execute(
            select(MetricPoint.service, func.avg(col), func.max(col), func.count())
            .where(MetricPoint.tenant_id == tenant_id)
            .group_by(MetricPoint.service)
            .order_by(func.avg(col).desc())
            .limit(max(1, min(int(limit), 50)))
        )).all()
        return [{"service": s, "metric": metric, "avg": round(float(a), 4),
                 "max": round(float(mx), 4), "count": int(c)} for s, a, mx, c in rows]


class ClickHouseTelemetryStore:
    """Same interface over ClickHouse HTTP (8123). Enabled when ASTRAEA_CLICKHOUSE_URL is set."""

    DDL = [
        """CREATE TABLE IF NOT EXISTS metric_points (
            tenant_id String, service String, ts DateTime64(3),
            request_rate Float32, error_rate Float32, p95_latency Float32, cpu Float32
        ) ENGINE = MergeTree ORDER BY (tenant_id, service, ts)""",
        """CREATE TABLE IF NOT EXISTS log_records (
            tenant_id String, service String, ts DateTime64(3), level String, message String
        ) ENGINE = MergeTree ORDER BY (tenant_id, service, ts)""",
        """CREATE TABLE IF NOT EXISTS deploy_events (
            tenant_id String, service String, ts DateTime64(3), kind String, description String
        ) ENGINE = MergeTree ORDER BY (tenant_id, service, ts)""",
    ]

    def __init__(self, db: AsyncSession):
        self.db = db  # session kept for symmetry; CH rows go over HTTP
        self.url = settings.clickhouse_url.rstrip("/")

    @staticmethod
    def _esc(value: str) -> str:
        """Escape a string literal for ClickHouse SQL (service/tenant ids are untrusted)."""
        return str(value).replace("\\", "\\\\").replace("'", "\\'")

    async def _query(self, sql: str, params: dict | None = None) -> list[dict]:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(self.url + "/", params={"query": sql}, content="")
            resp.raise_for_status()
            return [json.loads(l) for l in resp.text.splitlines() if l.strip()]

    async def ensure_tables(self) -> None:
        for ddl in self.DDL:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(self.url + "/", params={"query": ddl})

    async def add_point(self, tenant_id: str, service: str, m: dict[str, float]) -> None:
        row = {"tenant_id": tenant_id, "service": service,
               "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
               **{c: float(m[c]) for c in METRIC_COLUMNS}}
        await self._insert("metric_points", [row])

    async def add_log(self, tenant_id: str, service: str, level: str, message: str) -> None:
        await self._insert("log_records", [{"tenant_id": tenant_id, "service": service,
                                            "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
                                            "level": level, "message": message}])

    async def add_deploy(self, tenant_id: str, service: str, kind: str, description: str) -> None:
        await self._insert("deploy_events", [{"tenant_id": tenant_id, "service": service,
                                              "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
                                              "kind": kind, "description": description}])

    async def _insert(self, table: str, rows: list[dict]) -> None:
        body = "\n".join(json.dumps(r) for r in rows)
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                self.url + "/",
                params={"query": f"INSERT INTO {table} FORMAT JSONEachRow"},
                content=body,
            )
            resp.raise_for_status()

    async def window(self, tenant_id: str, service: str, limit: int = 120) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 1000))
        rows = await self._query(
            f"SELECT * FROM (SELECT * FROM metric_points WHERE tenant_id='{self._esc(tenant_id)}' "
            f"AND service='{self._esc(service)}' ORDER BY ts DESC LIMIT {limit}) ORDER BY ts ASC FORMAT JSONEachRow"
        )
        return [{**{c: float(r[c]) for c in METRIC_COLUMNS}, "ts": r["ts"]} for r in rows]

    async def logs(self, tenant_id: str, service: str, limit: int = 20) -> list[dict[str, str]]:
        limit = max(1, min(int(limit), 1000))
        return await self._query(
            f"SELECT level, message, toString(ts) AS ts FROM log_records WHERE tenant_id='{self._esc(tenant_id)}' "
            f"AND service='{self._esc(service)}' ORDER BY ts DESC LIMIT {limit} FORMAT JSONEachRow"
        )

    async def deploys(self, tenant_id: str, service: str, limit: int = 5) -> list[dict[str, str]]:
        limit = max(1, min(int(limit), 1000))
        return await self._query(
            f"SELECT kind, description, toString(ts) AS ts FROM deploy_events WHERE tenant_id='{self._esc(tenant_id)}' "
            f"AND service='{self._esc(service)}' ORDER BY ts DESC LIMIT {limit} FORMAT JSONEachRow"
        )

    async def top_services(self, tenant_id: str, metric: str = "error_rate",
                           limit: int = 5) -> list[dict]:
        metric = metric if metric in METRIC_COLUMNS else "error_rate"
        limit = max(1, min(int(limit), 50))
        rows = await self._query(
            f"SELECT service, avg({metric}) AS avg, max({metric}) AS max, count() AS count "
            f"FROM metric_points WHERE tenant_id='{self._esc(tenant_id)}' "
            f"GROUP BY service ORDER BY avg DESC LIMIT {limit} FORMAT JSONEachRow"
        )
        return [{"service": r["service"], "metric": metric,
                 "avg": round(float(r["avg"]), 4), "max": round(float(r["max"]), 4),
                 "count": int(r["count"])} for r in rows]


def get_store(db: AsyncSession):
    """ClickHouse when configured, sqlite otherwise — both real backends."""
    if settings.clickhouse_url:
        return ClickHouseTelemetryStore(db)
    return SqliteTelemetryStore(db)
