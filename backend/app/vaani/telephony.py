"""Telephony adapters for VAANI.

The gateway speaks one internal JSON protocol (`{"type":"audio","data":<b64 pcm16>}`
in, `{"type":"tts_audio","data":<b64 wav>}` out). A `TelephonyAdapter` translates a
carrier's wire frames to/from that protocol so the same full-duplex pipeline serves
the browser, Exotel AgentStream, or any future carrier.

`ExotelAdapter` implements Exotel's AgentStream bidirectional media protocol:
  inbound  {"event":"start"|"media"|"stop"|"mark", ...}
  outbound {"event":"media","media":{"payload":"<b64 pcm16>"}}
"""

from __future__ import annotations

import base64
import io
import wave

# Internal control markers the gateway understands from an adapter.
START = "__telephony_start__"
STOP = "__telephony_stop__"


class TelephonyAdapter:
    """Identity adapter: the browser already speaks the internal protocol."""

    name = "browser"

    def decode(self, frame: dict) -> dict | None:
        return frame

    def encode(self, event: dict) -> dict | None:
        return event


def _wav_to_pcm_b64(wav_b64: str) -> str:
    """Strip the WAV header, returning base64 raw PCM16 (what carriers stream)."""
    raw = base64.b64decode(wav_b64)
    try:
        with wave.open(io.BytesIO(raw), "rb") as w:
            return base64.b64encode(w.readframes(w.getnframes())).decode()
    except (wave.Error, EOFError):
        # already raw / unparseable — pass the bytes through untouched
        return wav_b64


class ExotelAdapter(TelephonyAdapter):
    name = "exotel"

    def decode(self, frame: dict) -> dict | None:
        event = frame.get("event")
        if event == "media":
            payload = (frame.get("media") or {}).get("payload", "")
            if not payload:
                return None
            return {"type": "audio", "data": payload}
        if event == "start":
            return {"type": START, "meta": frame.get("start") or {}}
        if event in ("stop", "clear"):
            return {"type": STOP}
        if event == "mark":
            return None
        # tolerate the internal protocol too (tests / mixed clients)
        if frame.get("type") in ("audio", "barge_in"):
            return frame
        return None

    def encode(self, event: dict) -> dict | None:
        etype = event.get("type")
        if etype == "tts_audio":
            return {"event": "media",
                    "media": {"payload": _wav_to_pcm_b64(event.get("data", ""))}}
        if etype == "tts_cancelled":
            return {"event": "clear"}
        # transcripts / metrics / control frames are not part of the media wire → drop
        return None


def get_adapter(name: str | None) -> TelephonyAdapter:
    return ExotelAdapter() if (name or "").lower() == "exotel" else TelephonyAdapter()
