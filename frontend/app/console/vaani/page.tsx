"use client";

import { useEffect, useRef, useState } from "react";
import { api, getToken, resolveWsBase } from "@/lib/api";

type Turn = { role: string; text: string };
type Booking = { id: number; customer_name: string; service: string; scheduled_for: string };

const TARGET_FRAMES = 3200;

export default function VaaniPage() {
  const [connected, setConnected] = useState(false);
  const [talking, setTalking] = useState(false);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [lat, setLat] = useState<{ stt_ms?: number; brain_ms?: number; total_ms?: number; target_ms?: number } | null>(null);
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [note, setNote] = useState("Press Call — speak after the first tone. Talk over VAANI to barge in.");
  const wsRef = useRef<WebSocket | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const playingRef = useRef(false);
  const audioElRef = useRef<HTMLAudioElement | null>(null);
  const bufferRef = useRef<Int16Array>(new Int16Array(0));

  async function loadBookings() {
    try {
      const b = await api<{ bookings: Booking[] }>("/api/vaani/bookings");
      setBookings(b.bookings);
    } catch (err) {
      setNote(err instanceof Error ? err.message : "bookings failed");
    }
  }
  useEffect(() => { loadBookings(); }, []);

  function pcmFromFloat(input: Float32Array): Int16Array {
    const out = new Int16Array(input.length);
    for (let i = 0; i < input.length; i++) {
      const s = Math.max(-1, Math.min(1, input[i]));
      out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }
    return out;
  }

  function startMic(ws: WebSocket) {
    navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } })
      .then((stream) => {
        const ctx = new AudioContext({ sampleRate: 16000 });
        audioCtxRef.current = ctx;
        const src = ctx.createMediaStreamSource(stream);
        const proc = ctx.createScriptProcessor(3200, 1, 1);
        proc.onaudioprocess = (e) => {
          const pcm = pcmFromFloat(e.inputBuffer.getChannelData(0));
          const merged = new Int16Array(bufferRef.current.length + pcm.length);
          merged.set(bufferRef.current); merged.set(pcm, bufferRef.current.length);
          bufferRef.current = merged;
          while (bufferRef.current.length >= TARGET_FRAMES && ws.readyState === 1) {
            const frame = bufferRef.current.slice(0, TARGET_FRAMES);
            bufferRef.current = bufferRef.current.slice(TARGET_FRAMES);
            ws.send(JSON.stringify({ type: "audio", data: Int16_to_b64(frame) }));
          }
          if (playingRef.current) {
            let sum = 0;
            for (let i = 0; i < pcm.length; i++) sum += pcm[i] * pcm[i];
            if (Math.sqrt(sum / pcm.length) > 900) ws.send(JSON.stringify({ type: "barge_in" }));
          }
        };
        src.connect(proc); proc.connect(ctx.destination);
      })
      .catch(() => setNote("microphone permission denied — VAANI needs the mic"));
  }

  function Int16_to_b64(arr: Int16Array): string {
    return btoa(String.fromCharCode(...new Uint8Array(arr.buffer)));
  }

  function b64_to_wav_url(b64: string): string {
    const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    return URL.createObjectURL(new Blob([bytes], { type: "audio/wav" }));
  }

  function connect() {
    (async () => {
      const base = await resolveWsBase();
      const ws = new WebSocket(`${base}/ws/vaani?token=${getToken()}`);
    wsRef.current = ws;
    ws.onopen = () => {
      setConnected(true);
      setNote("listening…");
      startMic(ws);
      const w = window as unknown as {
        SpeechRecognition?: new () => {
          continuous: boolean; interimResults: boolean; lang: string;
          onresult: ((e: { results: { length: number; [i: number]: { 0: { transcript: string } } } }) => void) | null;
          onend: (() => void) | null;
          start: () => void; stop: () => void;
        };
        webkitSpeechRecognition?: new () => {
          continuous: boolean; interimResults: boolean; lang: string;
          onresult: ((e: { results: { length: number; [i: number]: { 0: { transcript: string } } } }) => void) | null;
          onend: (() => void) | null;
          start: () => void; stop: () => void;
        };
      };
      const Ctor = w.SpeechRecognition || w.webkitSpeechRecognition;
      if (Ctor) {
        const rec = new Ctor();
        rec.continuous = true;
        rec.interimResults = false;
        rec.lang = "en-US";
        rec.onresult = (e) => {
          const text = e.results[e.results.length - 1][0].transcript.trim();
          if (text && ws.readyState === 1) ws.send(JSON.stringify({ type: "utterance", text }));
        };
        rec.onend = () => { if (ws.readyState === 1) try { rec.start(); } catch { /* already started */ } };
        try { rec.start(); } catch { /* unsupported */ }
      }
    };
    ws.onmessage = (m) => {
      const d = JSON.parse(m.data);
      if (d.type === "stt_final" && d.text) {
        setTurns((t) => [...t, { role: "caller", text: d.text }]);
        setLat((l) => ({ ...l, stt_ms: d.latency_ms }));
      } else if (d.type === "reply_sentence") {
        setTurns((t) => [...t, { role: "vaani", text: d.text }]);
        if (d.speak === "browser" && typeof window !== "undefined" && window.speechSynthesis) {
          window.speechSynthesis.cancel();
          const u = new SpeechSynthesisUtterance(d.text);
          playingRef.current = true;
          u.onend = () => { playingRef.current = false; };
          window.speechSynthesis.speak(u);
        }
      } else if (d.type === "tts_audio") {
        playingRef.current = true;
        const audio = audioElRef.current;
        if (audio) {
          audio.src = b64_to_wav_url(d.data);
          audio.play().catch(() => undefined);
          audio.onended = () => { playingRef.current = false; };
        }
      } else if (d.type === "metrics") {
        setLat({ stt_ms: d.stt_ms, brain_ms: d.brain_ms, total_ms: d.total_ms, target_ms: d.target_ms });
      } else if (d.type === "action") {
        setNote(`booked! booking #${d.result.booking_id} (durable run ${d.result.run_id?.slice(0, 8)}…)`);
        loadBookings();
      } else if (d.type === "tts_cancelled") {
        setNote(`barge-in handled in ${d.latency_ms}ms — listening to you again`);
      } else if (d.type === "error") {
        setNote(d.detail);
      }
    };
    ws.onclose = () => { setConnected(false); setNote("call ended"); };
    })();
  }

  function hangUp() {
    wsRef.current?.close();
    audioCtxRef.current?.close();
    audioCtxRef.current = null;
    if (typeof window !== "undefined" && window.speechSynthesis) window.speechSynthesis.cancel();
  }

  const totalLat = lat?.total_ms ?? 0;
  const targetLat = lat?.target_ms ?? 1500;

  return (
    <>
      <div className="pagehead">
        <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 6 }}>
          <span className={`dot ${connected ? "dot--live" : ""}`} />
          <span className="label label--accent">VAANI · VOICE AI EMPLOYEE</span>
          <span className="stamp stamp--phase">PHASE 5</span>
        </div>
        <h1 className="display">VAANI.</h1>
        <p>
          Browser speech (Web Speech API) plus Vertex/Gemini for the brain.
          Phone trunk (Exotel) is optional when{" "}
          <span className="mono">ASTRAEA_VAANI_TELEPHONY</span> is set.
        </p>
      </div>

      {/* ── Call control ── */}
      <div className="glass-card" style={{ padding: 18, marginBottom: 22 }}>
        <div style={{ display: "flex", gap: 16, alignItems: "center", flexWrap: "wrap" }}>
          <span className={`dot ${connected ? "dot--live" : ""}`} style={{ width: 12, height: 12 }} />
          <span style={{ flex: 1, fontSize: 13.5, color: "var(--ink-70)" }}>
            Try: &ldquo;Hi, I want to book a haircut for tomorrow at three pm&rdquo; — VAANI asks who&apos;s
            calling, books it, and the durable run lands in LOOM.
          </span>
          {!connected
            ? <button className="btn btn--accent" onClick={connect}>Call VAANI ☎</button>
            : <button className="btn" onClick={hangUp}>Hang up</button>}
        </div>
        {note && <p className="label label--ink" style={{ marginTop: 10 }}>{note}</p>}
      </div>

      {/* ── Instrument panel — latency budget ── */}
      <div className="instrument-grid">
        <div className="instrument glass-card">
          <p className="inst-label">STT latency</p>
          <div className="inst-value">{lat?.stt_ms ?? "—"}<span style={{ fontSize: 12 }}> ms</span></div>
        </div>
        <div className="instrument glass-card">
          <p className="inst-label">brain latency</p>
          <div className="inst-value">{lat?.brain_ms ?? "—"}<span style={{ fontSize: 12 }}> ms</span></div>
        </div>
        <div className="instrument glass-card">
          <p className="inst-label">total latency</p>
          <div className={`inst-value ${totalLat > targetLat ? "inst-value--accent" : ""}`}>
            {lat?.total_ms ?? "—"}<span style={{ fontSize: 12 }}> ms</span>
          </div>
          <p className="inst-trend">target &lt; {targetLat} ms</p>
        </div>
        <div className="instrument glass-card">
          <p className="inst-label">bookings</p>
          <div className="inst-value">{bookings.length}</div>
          <p className="inst-trend">made by voice</p>
        </div>
      </div>

      {/* ── Two columns: transcript + bookings ── */}
      <div className="split-2" style={{ marginBottom: 26 }}>
        {/* Transcript */}
        <div className="glass-card sheet" style={{ padding: 0, minHeight: 200 }}>
          <div style={{ padding: "10px 16px", borderBottom: "1px solid var(--line)" }}>
            <span className="label label--ink">CALL TRANSCRIPT</span>
          </div>
          <div style={{ maxHeight: 320, overflowY: "auto" }}>
            {turns.length === 0 && <div className="empty" style={{ margin: 18 }}>the live transcript appears here.</div>}
            {turns.map((t, i) => (
              <div key={i} style={{ padding: "6px 16px", borderBottom: "1px dotted var(--line)",
                                    display: "flex", gap: 10, alignItems: "baseline" }}>
                <span className={`stamp ${t.role === "vaani" ? "stamp--used" : ""}`} style={{ minWidth: 60, textAlign: "center" }}>
                  {t.role === "caller" ? "YOU" : "VAANI"}
                </span>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 13 }}>{t.text}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Bookings */}
        <div className="glass-card" style={{ padding: 0 }}>
          <div style={{ padding: "10px 16px", borderBottom: "1px solid var(--line)" }}>
            <span className="label label--ink">BOOKINGS MADE BY VOICE</span>
          </div>
          <div style={{ maxHeight: 320, overflowY: "auto" }}>
            {bookings.length === 0 && <div className="empty" style={{ margin: 18 }}>none yet — book one by voice.</div>}
            {bookings.slice(0, 10).map((b) => (
              <div key={b.id} style={{ padding: "8px 16px", borderBottom: "1px dotted var(--line)", fontSize: 13 }}>
                <span className="label" style={{ marginRight: 8 }}>#{b.id}</span>
                {b.customer_name} · {b.service} · {b.scheduled_for}
              </div>
            ))}
          </div>
        </div>
      </div>

      <audio ref={audioElRef} style={{ display: "none" }} />
    </>
  );
}
