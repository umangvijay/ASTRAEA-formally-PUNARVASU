"""Async engine + session + Base. sqlite (lite) and postgres (docker) share one code path."""

from __future__ import annotations

from sqlalchemy import event, inspect, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import StaticPool

from app.config import settings, ROOT


class Base(DeclarativeBase):
    pass


def _engine():
    from sqlalchemy.engine import make_url

    parsed = make_url(settings.db_url)
    kwargs: dict = {"echo": False}
    if parsed.drivername.startswith("sqlite") and parsed.database in (None, "", ":memory:"):
        kwargs["poolclass"] = StaticPool  # shared in-memory DB across sessions (tests)
    elif parsed.drivername.startswith("sqlite"):
        kwargs["connect_args"] = {"timeout": 30}  # busy-wait instead of failing on locks
    if parsed.drivername.startswith("postgresql"):
        kwargs["pool_size"] = 10
        kwargs["max_overflow"] = 20
        kwargs["connect_args"] = {"connect_timeout": 8}
    return create_async_engine(settings.db_url, **kwargs)


engine = _engine()


@event.listens_for(engine.sync_engine, "connect")
def _sqlite_pragmas(dbapi_conn, _):
    """WAL + busy timeout so file sqlite survives concurrent reader/writer sessions."""
    try:
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=30000")
        cur.close()
    except Exception:
        pass  # pragma support varies by driver; never block startup on it


SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    """Create tables if absent (dev convenience). Alembic is the canonical migration path."""
    if settings.db_url.startswith("sqlite+aiosqlite:///"):
        ROOT.mkdir(parents=True, exist_ok=True)
        settings.data_dir.mkdir(exist_ok=True)
    from app import models_registry  # noqa: F401 — register ALL tables on Base.metadata

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_stamp_alembic_if_empty)


def _stamp_alembic_if_empty(sync_conn) -> None:
    """create_all can precede Alembic. Stamp HEAD so the next upgrade is a no-op."""
    insp = inspect(sync_conn)
    if not insp.has_table("alembic_version"):
        sync_conn.execute(text(
            "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
        ))
    row = sync_conn.execute(text("SELECT version_num FROM alembic_version")).fetchone()
    if row:
        return
    head = "0010"
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        cfg = Config(str(ROOT / "backend" / "alembic.ini"))
        head = ScriptDirectory.from_config(cfg).get_current_head() or head
    except Exception:
        pass
    sync_conn.execute(text("INSERT INTO alembic_version (version_num) VALUES (:v)"), {"v": head})
