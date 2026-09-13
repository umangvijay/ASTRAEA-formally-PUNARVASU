"""Structured logging configuration for ASTRAEA.

In development, logs use the standard human-readable format.
In production (ASTRAEA_PROFILE=production), logs are emitted as JSON lines
suitable for ingestion by Loki, CloudWatch, or any log aggregator.

Usage:
    from app.shared.logging_config import configure_logging
    configure_logging()  # call once at startup
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

from app.config import settings


class JSONFormatter(logging.Formatter):
    """Emit structured JSON log lines for production log aggregators."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "module": record.module,
            "func": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = self.formatException(record.exc_info)
        # add any extra fields passed via `logger.info("msg", extra={"key": val})`
        for key in ("tenant_id", "run_id", "module_name", "service",
                     "duration_ms", "status_code", "method", "path"):
            val = getattr(record, key, None)
            if val is not None:
                log_entry[key] = val
        return json.dumps(log_entry, default=str)


class DevFormatter(logging.Formatter):
    """Compact, colored dev formatter with module context."""

    LEVEL_COLORS = {
        "DEBUG": "\033[90m",    # grey
        "INFO": "\033[36m",     # cyan
        "WARNING": "\033[33m",  # yellow
        "ERROR": "\033[31m",    # red
        "CRITICAL": "\033[91m", # bright red
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.LEVEL_COLORS.get(record.levelname, "")
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        level = record.levelname[:4].ljust(4)
        return f"{color}{ts} {level}{self.RESET} [{record.name}] {record.getMessage()}"


def configure_logging() -> None:
    """Set up root logger with appropriate formatter based on active profile."""
    root = logging.getLogger()

    # Don't add handlers if already configured (e.g. in tests)
    if root.handlers:
        return

    handler = logging.StreamHandler(sys.stdout)

    if settings.is_production:
        handler.setFormatter(JSONFormatter())
        root.setLevel(logging.INFO)
    else:
        handler.setFormatter(DevFormatter())
        root.setLevel(logging.DEBUG)

    root.addHandler(handler)

    # Quiet noisy libraries
    for name in ("httpx", "httpcore", "urllib3", "watchfiles",
                 "chromadb", "onnxruntime", "sentence_transformers"):
        logging.getLogger(name).setLevel(logging.WARNING)

    # Ensure key ASTRAEA loggers are always INFO+
    for name in ("astraea", "pulse", "shield", "medic", "sentinel",
                 "operator", "vaani", "forge", "loom", "shared"):
        logging.getLogger(name).setLevel(logging.INFO)
