"""Milestone 5 gate: VAANI telephony/DPDP + MODEL-FORGE GRPO reward.

All offline: the telephony translation, PII masking, consent, provider selection, and the
executable-SQL reward are exercised without a live call leg or a GPU.
"""

from __future__ import annotations

import base64
import io
import wave

from app.config import settings


# ── DPDP: PII masking + consent ──────────────────────────────────────────────
def test_mask_pii_redacts_indian_identifiers():
    from app.vaani.privacy import mask_pii

    text = ("call me on +91 9876543210, PAN ABCDE1234F, aadhaar 1234 5678 9012, "
            "card 4111 1111 1111 1111, email a@b.co")
    masked = mask_pii(text)
    assert "9876543210" not in masked and "[PHONE]" in masked
    assert "ABCDE1234F" not in masked and "[PAN]" in masked
    assert "1234 5678 9012" not in masked and "[AADHAAR]" in masked
    assert "[CARD]" in masked
    assert "a@b.co" not in masked and "[EMAIL]" in masked


def test_mask_turns_preserves_structure():
    from app.vaani.privacy import mask_turns

    turns = [{"role": "caller", "text": "my pan is ABCDE1234F", "kind": "x"}]
    out = mask_turns(turns)
    assert out[0]["role"] == "caller" and out[0]["kind"] == "x"
    assert "ABCDE1234F" not in out[0]["text"] and "[PAN]" in out[0]["text"]
    assert turns[0]["text"] == "my pan is ABCDE1234F"  # original untouched


def test_consent_notice_from_config():
    from app.vaani.privacy import consent_notice

    assert consent_notice() == settings.vaani_consent_notice


# ── Telephony: Exotel AgentStream translation ────────────────────────────────
def test_exotel_adapter_decodes_media_and_control():
    from app.vaani.telephony import START, STOP, ExotelAdapter

    a = ExotelAdapter()
    assert a.decode({"event": "media", "media": {"payload": "AAAA"}}) == {"type": "audio", "data": "AAAA"}
    assert a.decode({"event": "start", "start": {"callSid": "x"}})["type"] == START
    assert a.decode({"event": "stop"})["type"] == STOP
    assert a.decode({"event": "mark"}) is None


def test_exotel_adapter_encodes_tts_to_media():
    from app.vaani.telephony import ExotelAdapter

    # a tiny real WAV to encode
    pcm = b"\x01\x00" * 160
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(pcm)
    wav_b64 = base64.b64encode(buf.getvalue()).decode()

    frame = ExotelAdapter().encode({"type": "tts_audio", "no": 1, "data": wav_b64})
    assert frame["event"] == "media"
    assert base64.b64decode(frame["media"]["payload"]) == pcm  # header stripped → raw PCM
    # non-media frames are dropped on the telephony leg
    assert ExotelAdapter().encode({"type": "metrics", "total_ms": 900}) is None


def test_browser_adapter_is_identity():
    from app.vaani.telephony import get_adapter

    a = get_adapter(None)
    evt = {"type": "audio", "data": "AAAA"}
    assert a.decode(evt) == evt and a.encode(evt) == evt


# ── Sarvam provider selection (no network) ───────────────────────────────────
def test_sarvam_disabled_by_default_and_enables_with_config(monkeypatch):
    from app.vaani import sarvam

    assert sarvam.stt_enabled() is False and sarvam.tts_enabled() is False
    monkeypatch.setattr(settings, "sarvam_api_key", "sk-test")
    monkeypatch.setattr(settings, "vaani_stt_provider", "sarvam")
    monkeypatch.setattr(settings, "vaani_tts_provider", "sarvam")
    assert sarvam.stt_enabled() is True and sarvam.tts_enabled() is True


# ── MODEL-FORGE: executable-SQL GRPO reward ──────────────────────────────────
def test_sql_reward_and_group_advantages():
    from app.model_forge.data_gen import build_db, generate_tasks
    from app.model_forge.grpo_reward import (REWARD_CORRECT, REWARD_INVALID,
                                             REWARD_VALID_WRONG, group_advantages,
                                             score_group, sql_reward)

    task = generate_tasks(1, seed=7)[0]
    conn = build_db()

    assert sql_reward(task.gold_sql, task.expected_rows, conn) == REWARD_CORRECT
    assert sql_reward("SELECT bad syntax (((", task.expected_rows, conn) == REWARD_INVALID
    # valid SQL, wrong answer → partial credit
    assert sql_reward("SELECT -12345", task.expected_rows, conn) == REWARD_VALID_WRONG

    rewards, adv = score_group(
        [task.gold_sql, "SELECT -12345", "SELECT bad ((("], task.expected_rows, conn)
    assert rewards[0] == REWARD_CORRECT
    assert adv[0] == max(adv)  # the correct candidate has the highest advantage
    conn.close()

    assert group_advantages([]) == []
    assert group_advantages([1.0]) == [0.0]
    assert group_advantages([0.5, 0.5]) == [0.0, 0.0]


def test_register_champion_writes_registry():
    import pathlib

    from app.model_forge.serving import register_champion

    info = register_champion("/models/pvu-sql")
    assert info["provider"] == "model_forge" and info["model"] == "pvu-sql-champion"
    registry = pathlib.Path(settings.data_dir) / "forge" / "registry.json"
    assert registry.exists()
