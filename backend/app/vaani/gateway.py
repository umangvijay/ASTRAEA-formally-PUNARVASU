"""VAANI WebSocket gateway — the full-duplex voice endpoint.

Client protocol (JSON frames over WS):
  → {"type": "audio", "data": "<base64 PCM16 mono 16kHz>"}
  → {"type": "barge_in"}                       # user started talking over the reply
  ← {"type": "listening", "vad": "..."}        # session ready
  ← {"type": "utterance_start"}
  ← {"type": "stt_final", "text", "latency_ms"}
  ← {"type": "reply_sentence", "text", "no"}
  ← {"type": "tts_audio", "data": "<base64 wav>", "no"}
  ← {"type": "tts_cancelled", "latency_ms"}    # barge-in handled
  ← {"type": "metrics", "stt_ms", "brain_ms", "total_ms", "target_ms"}
  ← {"type": "action", "tool": "vaani.book", "result": {...}}

Bookings execute as durable engine runs (replayable, recorded); auto-approved by policy
for voice UX (ASTRAEA_VAANI_AUTO_APPROVE_BOOKINGS). Transcripts land in the DB and
LOOM, stamped FROM VAANI.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import event

from app.config import settings
from app.vaani import privacy
from app.vaani.audio import SAMPLE_RATE, get_transcriber, get_vad, synthesize
from app.vaani.brain import book, respond, sentences
from app.vaani.models import VaaniTranscript
from app.vaani.telephony import START, STOP, TelephonyAdapter, get_adapter

router = APIRouter(tags=["vaani"])

logger = logging.getLogger("vaani.gateway")

LATENCIES: dict[str, list[dict]] = {}  # tenant → rolling utterance latencies

# spoken only when the LLM chain is unreachable — honest degradation, never a script
_DEGRADED_REPLY = (
    "I'm sorry, my language service is unavailable right now. "
    "I'll take a message and we'll call you back."
)


class VoiceSession:
    """Utterance segmentation + conversation state for one call."""

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self.history: list[dict] = []
        self.turns: list[dict] = []
        self.buffer = b""
        self.in_utterance = False
        self.silence_ms = 0.0
        self.speech_frames = 0
        self.latencies: list[dict] = []          # per-utterance latency records
        self.tts_task: asyncio.Task | None = None  # current streaming TTS task (barge-in cancels it)

    def feed(self, pcm: bytes, vad_is_speech) -> tuple[bool, bool]:
        """Feed one frame. Returns (speech_active, utterance_complete)."""
        speech = vad_is_speech(pcm)
        if speech:
            self.speech_frames += 1
            self.silence_ms = 0.0
            if self.speech_frames >= 2 and not self.in_utterance:
                self.in_utterance = True
                self.buffer = b""
            if self.in_utterance:
                self.buffer += pcm
            return True, False
        if self.in_utterance:
            self.buffer += pcm
            self.silence_ms += 1000 * len(pcm) / 2 / SAMPLE_RATE
            collected = len(self.buffer) / 2 / SAMPLE_RATE
            # silence closes an utterance only after it holds at least ~1s of audio
            if self.silence_ms >= 500 and collected >= 1.0:
                self.in_utterance = False
                self.speech_frames = 0
                return False, True
        return False, False

    def take_utterance(self) -> bytes:
        buf, self.buffer = self.buffer, b""
        return buf


def _jwt_ok(token: str) -> str | None:
    import jwt as pyjwt

    try:
        payload = pyjwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return payload.get("tid")
    except pyjwt.PyJWTError:
        return None


@router.websocket("/ws/vaani")
async def vaani_ws(websocket: WebSocket, token: str = ""):
    """Browser full-duplex voice (internal JSON protocol)."""
    tenant_id = _jwt_ok(token)
    await websocket.accept()
    if tenant_id is None:
        await websocket.send_json({"type": "error",
                                   "detail": "invalid token; connect with ?token=<jwt>"})
        await websocket.close(code=4401)
        return
    await _serve(websocket, tenant_id, TelephonyAdapter())


@router.websocket("/ws/vaani/exotel")
async def vaani_exotel_ws(websocket: WebSocket, token: str = ""):
    """Telephony full-duplex voice over Exotel AgentStream (same pipeline, translated wire)."""
    tenant_id = _jwt_ok(token)
    await websocket.accept()
    if tenant_id is None:
        await websocket.close(code=4401)
        return
    await _serve(websocket, tenant_id, get_adapter("exotel"))


async def _serve(websocket: WebSocket, tenant_id: str, adapter: TelephonyAdapter) -> None:
    """The full-duplex voice loop, carrier-agnostic via `adapter`.

    `adapter.decode` turns inbound wire frames into the internal protocol; `adapter.encode`
    turns our outbound frames into the carrier's (dropping frames it doesn't carry, e.g.
    transcripts on a telephony leg)."""
    from app.db import SessionLocal

    async def send(obj: dict) -> None:
        out = adapter.encode(obj)
        if out is not None:
            await websocket.send_json(out)

    vad, vad_kind = get_vad()
    transcriber = get_transcriber()
    session = VoiceSession(tenant_id)
    await send({"type": "listening", "vad": vad_kind})

    # ── DPDP: announce consent at t0 and record it as the first turn ──
    notice = privacy.consent_notice()
    session.turns.append({"role": "assistant", "text": notice, "kind": "consent"})
    await send({"type": "consent", "text": notice})
    try:
        consent_wav = await synthesize(notice)
        await send({"type": "tts_audio", "no": -1,
                    "data": base64.b64encode(consent_wav).decode()})
    except Exception:  # noqa: BLE001 — spoken consent is best-effort; the notice frame stands
        pass

    cancelled = False
    barge_in_ts: float | None = None

    async def send_reply(sent: str, no: int) -> None:
        t = time.perf_counter()
        wav = await synthesize(sent)
        if cancelled:
            return
        await send({"type": "reply_sentence", "text": sent, "no": no})
        await send({"type": "tts_audio", "no": no, "data": base64.b64encode(wav).decode()})
        session.latencies.append({"tts_ms": round((time.perf_counter() - t) * 1000, 1)})

    try:
        while True:
            msg = await websocket.receive()
            if msg["type"] == "websocket.disconnect":
                break
            try:
                raw = json.loads(msg.get("text") or "{}")
            except json.JSONDecodeError:
                continue
            data = adapter.decode(raw)
            if data is None:
                continue
            if data.get("type") == START:
                continue  # carrier stream opened — nothing to do, keep listening
            if data.get("type") == STOP:
                break

            if data.get("type") == "barge_in":
                cancelled = True
                barge_in_ts = time.perf_counter()
                if session.tts_task and not session.tts_task.done():
                    session.tts_task.cancel()
                cancel_ms = round((time.perf_counter() - barge_in_ts) * 1000, 1)
                session.latencies.append({"barge_in_cancel_ms": cancel_ms})
                await send({"type": "tts_cancelled", "latency_ms": cancel_ms})
                continue

            if data.get("type") != "audio":
                continue
            pcm = base64.b64decode(data.get("data", ""))
            speech, complete_utt = session.feed(pcm, vad.is_speech)
            if speech and session.speech_frames == 2 and session.in_utterance:
                await send({"type": "utterance_start"})
            if not complete_utt:
                continue

            utterance = session.take_utterance()
            t0 = time.perf_counter()
            try:
                text = await asyncio.to_thread(transcriber.transcribe, utterance)
            except Exception as exc:  # noqa: BLE001 — STT down must not kill the call
                logger.warning("vaani stt failed: %s", exc)
                await send({"type": "error", "detail": "transcription failed — try again"})
                continue
            stt_ms = round((time.perf_counter() - t0) * 1000, 1)
            await send({"type": "stt_final", "text": text, "latency_ms": stt_ms})
            if not text:
                continue
            session.turns.append({"role": "caller", "text": text})

            tb = time.perf_counter()
            try:
                async with SessionLocal() as db:
                    turn = await respond(db, tenant_id, session.history, text)
            except Exception as exc:  # noqa: BLE001 — degrade with a spoken apology, never a dead socket
                logger.warning("vaani brain failed: %s", exc)
                await send({"type": "error", "detail": f"brain unavailable ({str(exc)[:120]})"})
                await send({"type": "reply_sentence", "text": _DEGRADED_REPLY, "no": 0})
                cancelled = False
                continue
            brain_ms = round((time.perf_counter() - tb) * 1000, 1)
            reply = turn["reply"]
            session.history.append({"role": "caller", "text": text})
            session.history.append({"role": "assistant", "text": reply})
            session.turns.append({"role": "assistant", "text": reply})

            cancelled = False
            total_ms = round((time.perf_counter() - t0) * 1000, 1)
            await send({"type": "metrics", "stt_ms": stt_ms,
                        "brain_ms": brain_ms, "total_ms": total_ms,
                        "target_ms": settings.vaani_latency_target_ms})
            LATENCIES.setdefault(tenant_id, []).append(
                {"stt_ms": stt_ms, "brain_ms": brain_ms, "total_ms": total_ms})
            LATENCIES[tenant_id] = LATENCIES[tenant_id][-200:]

            booking = turn.get("booking")
            if booking:
                from app.core import engine
                from app.core.models import Run

                steps = engine.validate_workflow([
                    {"name": "book", "type": "tool", "tool": "vaani.book",
                     "args": {"booking_json": json.dumps(booking, default=str)}},
                ])
                run = Run(tenant_id=tenant_id,
                          goal=f"Voice booking: {booking.get('customer_name')} — {booking.get('service')}",
                          workflow=steps, origin_module="vaani")
                async with SessionLocal() as db:
                    db.add(run)
                    await db.commit()
                    await db.refresh(run)
                    run_id = run.id
                await engine.execute(run_id)  # durable + replayable; auto-approved by policy
                async with SessionLocal() as db:
                    r2 = await db.get(Run, run_id)
                    payload = json.loads(((r2.result or {}).get("outputs", {}) or {}).get("book", "{}") or "{}")
                if payload:
                    await send({"type": "action", "tool": "vaani.book",
                                "result": {**payload, "run_id": run_id}})
                    session.turns.append({"role": "action",
                                          "text": json.dumps(payload, default=str)})

            for no, sent in enumerate(sentences(reply)):
                if cancelled:
                    break
                session.tts_task = asyncio.get_running_loop().create_task(send_reply(sent, no))
                try:
                    await session.tts_task
                except asyncio.CancelledError:
                    break
    except WebSocketDisconnect:
        pass
    finally:
        if session.turns:
            # DPDP: mask Aadhaar/PAN/phone/card/email before anything is persisted
            turns = privacy.mask_turns(session.turns) if settings.vaani_pii_masking else session.turns
            async with SessionLocal() as db:
                db.add(VaaniTranscript(tenant_id=tenant_id, turns=turns,
                                       latencies={"p": session.latencies}))
                await db.commit()
