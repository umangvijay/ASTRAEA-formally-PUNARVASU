"""Test fixtures: file-based sqlite (WAL) app + async client. No docker, no network."""

from __future__ import annotations

import os
import pathlib as _pl
import tempfile

import pytest
from httpx import ASGITransport, AsyncClient

# must be set before app modules import config
_test_db = _pl.Path(tempfile.gettempdir()) / f"astraea-test-{os.getpid()}.db"
if _test_db.exists():
    _test_db.unlink()
os.environ["ASTRAEA_DATABASE_URL"] = f"sqlite+aiosqlite:///{_test_db}"
os.environ.setdefault("ASTRAEA_JWT_SECRET", "astraea-test-jwt-secret-key-32ok")
os.environ.setdefault("ASTRAEA_DEMO_DATA", tempfile.mkdtemp(prefix="pvu-demo-"))
os.environ.setdefault("ASTRAEA_DATA_DIR_OVERRIDE", tempfile.mkdtemp(prefix="pvu-data-"))  # isolate from the live platform's data (trained models, benchmark files)  # isolate demo config files
os.environ.setdefault("ASTRAEA_ANOMALY_COOLDOWN_SECONDS", "0")
os.environ.setdefault("ASTRAEA_SHIELD_INCIDENT_COOLDOWN_SECONDS", "0")
os.environ.setdefault("ASTRAEA_LLM_PROVIDER_ORDER", "gemini,groq,ollama")  # tests: fast + deterministic  # let the 10-fault gate fire back-to-back

from app.operator.executor import ensure_playwright_browsers  # noqa: E402

ensure_playwright_browsers()

from app.db import Base, engine, init_db  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest.fixture()
async def app():
    await init_db()
    from app.db import SessionLocal
    from app.shared.seed import seed, seed_shield

    async with SessionLocal() as db:
        await seed(db)
        await seed_shield(db)
    yield create_app()
    from app.core import engine as run_engine

    await run_engine.wait_all()  # background runs must not hold locks during teardown
    await engine.dispose()
    if _test_db.exists():
        _test_db.unlink()


@pytest.fixture()
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture()
async def db_session(app):
    """A live DB session over the initialized+seeded test app (used by cross-module tests)."""
    from app.db import SessionLocal

    async with SessionLocal() as session:
        yield session


@pytest.fixture()
async def auth_headers(client) -> dict[str, str]:
    resp = await client.post(
        "/api/auth/register",
        json={"email": "umang@test.dev", "password": "Correct-Horse-42", "full_name": "Umang Vijay"},
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
