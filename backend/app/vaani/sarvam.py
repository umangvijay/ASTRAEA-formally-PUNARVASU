"""Optional Sarvam AI (Indic) STT/TTS for VAANI — Saaras (STT) and Bulbul (TTS).

Enabled per-provider via config (`vaani_stt_provider`/`vaani_tts_provider` == "sarvam"
and `SARVAM_API_KEY` set). Everything degrades to faster-whisper / Piper / macOS `say`
when the key is absent or a call fails — never a dead call leg.
"""

from __future__ import annotations

import base64
import io
import logging
import wave

import httpx

from app.config import settings

logger = logging.getLogger("vaani.sarvam")

_STT_URL = "https://api.sarvam.ai/speech-to-text"
_TTS_URL = "https://api.sarvam.ai/text-to-speech"
SAMPLE_RATE = 16000


def stt_enabled() -> bool:
    return settings.vaani_stt_provider == "sarvam" and bool(settings.sarvam_api_key)


def tts_enabled() -> bool:
    return settings.vaani_tts_provider == "sarvam" and bool(settings.sarvam_api_key)


def _pcm_to_wav(pcm16: bytes) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm16)
    return buf.getvalue()


async def transcribe(pcm16: bytes, *, language_code: str = "en-IN") -> str:
    """Saaras STT. Raises on failure so the caller can fall back to whisper."""
    wav = _pcm_to_wav(pcm16)
    headers = {"api-subscription-key": settings.sarvam_api_key}
    files = {"file": ("audio.wav", wav, "audio/wav")}
    data = {"language_code": language_code, "model": "saaras:v2"}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(_STT_URL, headers=headers, data=data, files=files)
        resp.raise_for_status()
        body = resp.json()
    return str(body.get("transcript", "")).strip()


async def synthesize(text: str, *, language_code: str = "en-IN") -> bytes:
    """Bulbul TTS → WAV bytes. Raises on failure so the caller can fall back to Piper/say."""
    headers = {"api-subscription-key": settings.sarvam_api_key,
               "Content-Type": "application/json"}
    payload = {"inputs": [text], "target_language_code": language_code,
               "speaker": "meera", "model": "bulbul:v2",
               "speech_sample_rate": SAMPLE_RATE}
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(_TTS_URL, headers=headers, json=payload)
        resp.raise_for_status()
        body = resp.json()
    audios = body.get("audios") or []
    if not audios:
        raise RuntimeError("sarvam tts returned no audio")
    return base64.b64decode(audios[0])
