"""Durable artifact storage — patches, champion state, anything that must
survive an ephemeral container.

Backends, in priority order:
- GCS  when ASTRAEA_ARTIFACT_BUCKET is set and google-cloud-storage imports
       (the Cloud Run path: containers die, the bucket does not).
- local filesystem under data/artifacts otherwise (laptop, docker, tests).

Callers get back a durable reference (`gs://bucket/…` or an absolute path) that
reads back through `read_text` from any instance. Never raises on the write
path callers can't recover from — returns the local path on GCS failure so the
operation still completes, degraded but honest (the reference is real either way).
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.config import settings

logger = logging.getLogger("artifacts")

_client = None
_client_checked = False


def _gcs_client():
    global _client, _client_checked
    if _client_checked:
        return _client
    _client_checked = True
    if not settings.artifact_bucket:
        return None
    try:
        from google.cloud import storage  # noqa: PLC0415 — optional cloud dep

        _client = storage.Client()
    except Exception as exc:  # noqa: BLE001 — degrade to local, say so once
        logger.warning("artifacts: GCS unavailable (%s) — storing locally", str(exc)[:100])
        _client = None
    return _client


def backend_name() -> str:
    return "gcs" if _gcs_client() is not None else "local"


def _local_path(rel: str) -> Path:
    path = settings.data_dir / "artifacts" / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def write_text(rel: str, text: str) -> str:
    """Store text durably; returns the durable reference (gs:// or local path)."""
    client = _gcs_client()
    if client is not None:
        try:
            blob = client.bucket(settings.artifact_bucket).blob(rel)
            blob.upload_from_string(text, content_type="application/json"
                                    if rel.endswith(".json") else "text/plain")
            return f"gs://{settings.artifact_bucket}/{rel}"
        except Exception:  # noqa: BLE001 — local fallback keeps the operation alive
            logger.warning("artifacts: GCS write failed for %s — local fallback", rel,
                           exc_info=True)
    local = _local_path(rel)
    local.write_text(text)
    return str(local)


def read_text(ref: str) -> str | None:
    """Read back by durable reference or repo-relative path. None when missing."""
    if ref.startswith("gs://"):
        client = _gcs_client()
        if client is None:
            return None
        try:
            _, bucket, _, rel = ref.split("/", 3)
            return client.bucket(bucket).blob(rel).download_as_text()
        except Exception:  # noqa: BLE001 — missing/unreadable artifact reads as absent
            return None
    path = Path(ref)
    if not path.is_absolute():
        path = settings.data_dir / "artifacts" / ref
    try:
        return path.read_text()
    except OSError:
        return None
