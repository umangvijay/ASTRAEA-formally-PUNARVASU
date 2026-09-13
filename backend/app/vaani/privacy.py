"""DPDP Act 2023 helpers for VAANI: consent notice + PII masking.

Transcripts are masked BEFORE they are persisted, so raw Aadhaar / PAN / phone /
card numbers never land in long-term storage. Masking runs on both the browser and
telephony paths.
"""

from __future__ import annotations

import re

from app.config import settings

# Order matters: match the longest / most specific patterns first so a 12-digit
# Aadhaar isn't partially consumed by the 10-digit phone matcher, etc.
_PAN = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")
_CARD = re.compile(r"\b(?:\d[ -]?){13,16}\b")
_AADHAAR = re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b")
_PHONE = re.compile(r"(?:\+?91[-\s]?)?\b[6-9]\d{9}\b")
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")


def mask_pii(text: str) -> str:
    """Redact Indian PII markers from a string. Idempotent and safe on empty input."""
    if not text:
        return text
    out = _PAN.sub("[PAN]", text)
    out = _CARD.sub("[CARD]", out)
    out = _AADHAAR.sub("[AADHAAR]", out)
    out = _PHONE.sub("[PHONE]", out)
    out = _EMAIL.sub("[EMAIL]", out)
    return out


def mask_turns(turns: list[dict]) -> list[dict]:
    """Return a masked copy of conversation turns (never mutates the originals)."""
    masked: list[dict] = []
    for turn in turns:
        item = dict(turn)
        if isinstance(item.get("text"), str):
            item["text"] = mask_pii(item["text"])
        masked.append(item)
    return masked


def consent_notice() -> str:
    return settings.vaani_consent_notice
