"""VAANI gate: real-speech STT, sentence TTS, VAD segmentation, 10 conversations with
bookings (provider-driven replies — VAANI's code never composes conversation text itself),
transcripts + LOOM provenance."""

from __future__ import annotations

import asyncio
import io
import json
import random
import struct
import wave

import random as _r

import pytest

from app.config import settings
from app.shared.security import decode_access_token
from app.vaani.audio import FRAME_SAMPLES, SAMPLE_RATE, get_vad, synthesize
from app.vaani.brain import book, respond, sentences
from app.vaani.gateway import VoiceSession
from app.db import SessionLocal
from sqlalchemy import select


def _tid(auth_headers) -> str:
    return decode_access_token(auth_headers["Authorization"].removeprefix("Bearer "))["tid"]


def _spoken_wav(text: str) -> bytes:
    """Real speech via macOS `say` — actual audio, not a fixture file."""
    import subprocess
    import tempfile
    from pathlib import Path

    tmp = Path(tempfile.mkdtemp())
    aiff, wav = tmp / "s.aiff", tmp / "s.wav"
    subprocess.run(["say", "-v", "Samantha", "-o", str(aiff), text], check=True, timeout=20)
    subprocess.run(["afconvert", str(aiff), "-f", "WAVE", "-d", "LEI16@16000", str(wav)],
                   check=True, timeout=20)
    data = wav.read_bytes()
    return data


def _wav_to_pcm16(data: bytes) -> bytes:
    with wave.open(io.BytesIO(data), "rb") as w:
        assert w.getframerate() == SAMPLE_RATE
        return w.readframes(w.getnframes())


def _speech_frames() -> list[bytes]:
    """Real spoken audio, sliced into 512-sample silero frames."""
    pcm = _wav_to_pcm16(_spoken_wav("I would like to book an appointment for tomorrow please"))
    return [pcm[i:i + FRAME_SAMPLES * 2] for i in range(0, len(pcm) - FRAME_SAMPLES * 2, FRAME_SAMPLES * 2)]


def test_vad_segments_speech_from_silence():
    vad, kind = get_vad()
    silence = b"".join(struct.pack("<h", _r.randint(-25, 25)) for _ in range(FRAME_SAMPLES))  # ambient noise floor
    frames = _speech_frames()
    speech_votes = [vad.is_speech(f) for f in frames]
    assert not vad.is_speech(silence), "silence must not be speech"
    assert sum(speech_votes) >= len(frames) * 0.5, (
        f"spoken frames must mostly register as speech (got {sum(speech_votes)}/{len(frames)}, vad={kind})")


def test_tts_produces_real_audio():
    wav = asyncio.run(synthesize("Your booking is confirmed."))
    assert wav[:4] == b"RIFF" and len(wav) > 2000


def test_sentences_split():
    parts = sentences("Sure thing. I can do Thursday at five. See you then!")
    assert len(parts) == 3


async def test_real_speech_stt():
    """Real spoken audio through faster-whisper — the honest STT gate."""
    from app.vaani.audio import get_transcriber

    wav = _spoken_wav("hello world from astraea")
    pcm = _wav_to_pcm16(wav)
    try:
        text = await asyncio.to_thread(get_transcriber().transcribe, pcm)
    except Exception as exc:  # noqa: BLE001 — model download is env, not product
        name = type(exc).__name__
        if "Proxy" in name or "403" in str(exc) or "download" in str(exc).lower():
            pytest.skip(f"whisper model unavailable: {exc}")
        raise
    lowered = text.lower()
    assert "hello" in lowered and "world" in lowered, f"transcription was: {text!r}"


async def test_voice_session_segments_utterances(app, auth_headers):
    vad, _ = get_vad()
    session = VoiceSession("t1")
    quiet = b"".join(struct.pack("<h", _r.randint(-25, 25)) for _ in range(FRAME_SAMPLES))  # ambient floor
    complete = False
    for frame in _speech_frames():  # real speech stream
        _, complete = session.feed(frame, vad.is_speech)
        if complete:
            break
    if not complete:
        assert session.in_utterance, "speech must open an utterance"
        for _ in range(40):  # ~1.2s silence → closes the utterance
            _, complete = session.feed(quiet, vad.is_speech)
            if complete:
                break
    assert complete, "silence after speech must close the utterance"
    pcm = session.take_utterance()
    assert len(pcm) > 1000


async def test_ten_conversations_with_bookings(app, auth_headers, monkeypatch):
    """The conversation gate: 10 turns where every reply comes from the provider and
    bookings execute as durable rows + LOOM artifacts. No reply text lives in VAANI's code."""
    from app.sentinel import llm as sentinel_llm

    conversations = []
    for i in range(10):
        conversations.append([
            {"role": "caller", "text": f"hi, I want to book a haircut for customer{i}"},
            {"role": "assistant", "text": f"PROVIDER-REPLY-turn1-{i}"},
            {"role": "caller", "text": "tomorrow at three pm"},
            {"role": "assistant", "text": f"PROVIDER-REPLY-turn2-{i}"},
        ])

    async def fake_complete(db, tenant_id, messages, **kwargs):
        last_user = [m for m in messages if m["role"] == "user"][-1]["content"]
        # the provider decides: only when it has seen the time does it emit the booking
        if "tomorrow" in last_user:
            return {"content": json.dumps({
                "reply": f"PROVIDER-REPLY-confirmed-{tenant_id[:4]}",
                "booking": {"customer_name": f"customer{random_suffix[0]}",
                            "service": "haircut", "scheduled_for": "tomorrow 3pm"},
            }), "provider": "test-double", "usage": {}}
        return {"content": json.dumps({"reply": "PROVIDER-REPLY-ask-time", "booking": None}),
                "provider": "test-double", "usage": {}}

    random_suffix = [str(i) for i in range(10)]
    monkeypatch.setattr(sentinel_llm, "complete", fake_complete)

    tenant_id = _tid(auth_headers)
    bookings = []
    for i in range(10):
        async with SessionLocal() as db:
            turn = await respond(db, tenant_id, conversations[i][:2], conversations[i][2]["text"])
        assert turn["reply"].startswith("PROVIDER-REPLY"), "reply did not come from the provider"
        conversations[i].append({"role": "assistant", "text": turn["reply"]})

        assert turn["booking"] is not None, "provider decided a booking — none executed"
        async with SessionLocal() as db:
            result = await book(db, tenant_id, turn["booking"])
        bookings.append(result)

    assert len(bookings) == 10
    async with SessionLocal() as db:
        from app.vaani.models import VaaniBooking

        rows = (await db.execute(select(VaaniBooking))).scalars().all()
        assert len(rows) == 10
        from app.loom.models import LoomItem

        loom_items = (await db.execute(
            select(LoomItem).where(LoomItem.kind == "booking")
        )).scalars().all()
        assert len(loom_items) == 10
        assert all(i.origin_module == "vaani" for i in loom_items)
