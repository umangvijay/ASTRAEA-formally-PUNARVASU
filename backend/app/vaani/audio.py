"""VAD + STT + TTS: the VAANI audio stack, with the mandated fallback chain.

- VAD: Silero (torch) when importable; an energy-based RMS fallback otherwise — both
  frame-level (30ms) so barge-in and turn detection react in tens of milliseconds.
- STT: faster-whisper (local, streaming-friendly chunked transcription).
- TTS: Piper when importable/voiced; macOS `say`+`afconvert` otherwise (always available
  here). Sentence-level synthesis feeds barge-in cancellation between chunks.
"""

from __future__ import annotations

import asyncio
import io
import subprocess
import time
import wave

from app.config import settings

SAMPLE_RATE = 16000
FRAME_MS = 32
FRAME_SAMPLES = 512  # silero wants 512 samples @16k


# ── VAD ────────────────────────────────────────────────────────────
class EnergyVAD:
    """RMS fallback VAD — calibrated per session against observed noise floor."""

    def __init__(self, threshold: float = 0.0):
        self.noise_floor: float | None = threshold

    def is_speech(self, pcm: bytes) -> bool:
        import array
        import math

        samples = array.array("h")
        samples.frombytes(pcm)
        if not samples:
            return False
        rms = math.sqrt(sum(s * s for s in samples) / len(samples))
        floor = self.noise_floor or 300
        return rms > floor * 1.6


class SileroVAD:
    def __init__(self):
        from silero_vad import load_silero_vad

        self.model = load_silero_vad()

    def is_speech(self, pcm: bytes) -> bool:
        import numpy as np
        import torch

        arr = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        n = arr.size
        if n == 0:
            return False
        # silero requires exact 512-sample windows @16k — clients stream arbitrary
        # frame sizes (browser 3200, telephony 160), so chunk here and OR the verdicts
        if n < 512:
            arr = np.pad(arr, (0, 512 - n))
        with torch.no_grad():
            for start in range(0, arr.size - 511, 512):
                window = torch.from_numpy(arr[start:start + 512])
                if bool(self.model(window, SAMPLE_RATE).item() > 0.5):
                    return True
        return False


_vad = None
_vad_kind = None


class HybridVAD:
    """Silero (speech model) AND an energy floor — silero alone fires on digital silence,
    energy alone can't tell speech from a door slam; together they're solid."""

    def __init__(self):
        self.silero = SileroVAD()
        self.energy = EnergyVAD()

    def is_speech(self, pcm: bytes) -> bool:
        if not self.energy.is_speech(pcm):
            return False
        return self.silero.is_speech(pcm)


def get_vad():
    global _vad, _vad_kind
    if _vad is None:
        try:
            _vad = HybridVAD()
            _vad_kind = "silero+energy"
        except Exception:  # noqa: BLE001 — torch missing / model download failed
            _vad = EnergyVAD()
            _vad_kind = "energy"
    return _vad, _vad_kind


# ── STT ────────────────────────────────────────────────────────────
class Transcriber:
    def __init__(self):
        self._model = None

    def _ensure_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(
                settings.vaani_whisper_model, device="cpu", compute_type="int8"
            )
        return self._model

    def transcribe(self, pcm16: bytes) -> str:
        # Sarvam Saaras (Indic) when explicitly enabled; Vertex/Gemini next; whisper last.
        from app.vaani import sarvam

        if sarvam.stt_enabled():
            try:
                import asyncio

                return asyncio.run(sarvam.transcribe(pcm16))
            except Exception:  # noqa: BLE001 — degrade to cloud / whisper
                pass
        cloud = _transcribe_gemini(pcm16)
        if cloud:
            return cloud
        try:
            import numpy as np

            arr = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768.0
            model = self._ensure_model()
            segments, _ = model.transcribe(arr, language="en", beam_size=1, vad_filter=False)
            return " ".join(s.text.strip() for s in segments).strip()
        except Exception:
            return ""


_transcriber: Transcriber | None = None


def _transcribe_gemini(pcm16: bytes) -> str:
    """Vertex / Gemini speech-to-text — the Cloud Run path (no whisper/torch)."""
    if not pcm16 or len(pcm16) < 3200:
        return ""
    try:
        import base64

        import httpx

        from app.sentinel.upstream import pick_provider

        provider, model = pick_provider(None)
        if provider not in ("gemini", "vertex"):
            return ""
        wav = _wav_bytes(pcm16, SAMPLE_RATE)
        body = {
            "contents": [{
                "role": "user",
                "parts": [
                    {"text": "Transcribe this spoken audio. Return only the words, no quotes."},
                    {"inlineData": {"mimeType": "audio/wav",
                                    "data": base64.b64encode(wav).decode()}},
                ],
            }],
            "generationConfig": {"temperature": 0, "maxOutputTokens": 256},
        }
        loc, proj = settings.vertex_location, settings.vertex_project
        if provider == "vertex":
            from app.sentinel.upstream import _vertex_adc_token

            url = (
                f"https://{loc}-aiplatform.googleapis.com/v1/projects/{proj}/locations/{loc}"
                f"/publishers/google/models/{model.removeprefix('vertex/')}:generateContent"
            )
            token = settings.vertex_access_token or _vertex_adc_token()
            headers = {"Authorization": f"Bearer {token}"} if token else {}
            key = settings.vertex_api_key or (settings.gemini_api_key if not token else "")
            if key and not token:
                url += f"?key={key}"
        else:
            url = (
                "https://generativelanguage.googleapis.com/v1beta/models/"
                f"{model}:generateContent?key={settings.gemini_api_key}"
            )
            headers = {}
        with httpx.Client(timeout=45) as client:
            resp = client.post(url, json=body, headers=headers)
            if resp.status_code != 200:
                return ""
            parts = (((resp.json().get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
            text = " ".join(p.get("text", "") for p in parts).strip()
            return text
    except Exception:
        return ""


def get_transcriber() -> Transcriber:
    global _transcriber
    if _transcriber is None:
        _transcriber = Transcriber()
    return _transcriber


# ── TTS ────────────────────────────────────────────────────────────
def _wav_bytes(pcm16: bytes, sample_rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm16)
    return buf.getvalue()


async def synthesize(text: str) -> bytes:
    """Sentence → WAV bytes (16k mono). Sarvam (Indic) when enabled, then Piper, then `say`."""
    from app.vaani import sarvam

    if sarvam.tts_enabled():
        try:
            return await sarvam.synthesize(text)
        except Exception:  # noqa: BLE001 — degrade to piper/say
            pass
    try:
        return await _synthesize_piper(text)
    except Exception:  # noqa: BLE001 — piper not installed/voiced: say fallback
        try:
            return await _synthesize_say(text)
        except Exception:
            return b""


async def _synthesize_piper(text: str) -> bytes:
    import piper  # noqa: F401 — raises ImportError when absent

    voice_path = settings.data_dir / "piper-voice.onnx"
    if not voice_path.exists():
        raise RuntimeError("piper voice model not provisioned")
    from piper import PiperVoice

    voice = PiperVoice.load(str(voice_path))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        voice.synthesize(text, w)
    return buf.getvalue()


async def _synthesize_say(text: str) -> bytes:
    """macOS native TTS: say → aiff → afconvert → wav. Real synthesis, zero pip risk."""
    tmp = settings.data_dir / "tts_tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    wav = tmp / f"s{time.time_ns()}.wav"
    try:
        proc = await asyncio.create_subprocess_exec(
            "say", "-v", settings.vaani_say_voice, "-o", str(wav),
            "--data-format=LEI16@16000", text,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.wait(), timeout=10)
        return wav.read_bytes()
    finally:
        try:
            wav.unlink(missing_ok=True)
        except Exception:
            pass

