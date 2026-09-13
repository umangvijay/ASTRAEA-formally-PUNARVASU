"""Cloud Run entrypoint — bind PORT even when the full app fails to import.

`uvicorn app.cloud_run:app` so a missing JWT secret or a bad DATABASE_URL
returns JSON 503 on /health instead of Google Frontend's opaque HTML 500.
"""
from __future__ import annotations

import traceback

from fastapi import FastAPI
from fastapi.responses import JSONResponse

try:
    from app.main import app
except Exception as exc:  # noqa: BLE001 — this file exists to surface boot errors
    _failed = FastAPI(title="Astraea boot failure")
    _payload = {
        "status": "boot_failed",
        "error": str(exc),
        "trace": traceback.format_exc()[-4000:],
    }

    @_failed.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
    async def _fail(path: str = ""):  # noqa: ARG001
        return JSONResponse(_payload, status_code=503)

    app = _failed
