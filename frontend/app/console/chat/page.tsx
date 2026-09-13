"use client";

import { FormEvent, useState } from "react";
import { ApiError, api } from "@/lib/api";

type Msg = { role: "user" | "assistant"; content: string };

export default function ChatPage() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  async function send(e: FormEvent) {
    e.preventDefault();
    const content = text.trim();
    if (!content) {
      setNote("Type a message — empty content is rejected by SENTINEL.");
      return;
    }
    const next = [...messages, { role: "user" as const, content }];
    setMessages(next);
    setText("");
    setBusy(true);
    setNote(null);
    try {
      const body = await api<{
        choices?: { message?: { content?: string }; finish_reason?: string }[];
        error?: { message?: string };
        astraea?: { provider?: string; model?: string };
      }>("/v1/chat/completions", {
        method: "POST",
        body: JSON.stringify({ messages: next, stream: false }),
      });
      const reply = body.choices?.[0]?.message?.content?.trim();
      if (!reply) {
        setNote(body.error?.message || "The model returned no content.");
        return;
      }
      const who = body.astraea?.provider
        ? `${body.astraea.provider}/${body.astraea.model ?? ""}`
        : "sentinel";
      setMessages([...next, { role: "assistant", content: `${reply}\n\n— ${who}` }]);
    } catch (err) {
      if (err instanceof ApiError && err.status === 503) {
        setNote("No general model is configured. Connect Vertex, Gemini, Groq or Ollama — the SQL champion is not used for chat.");
      } else {
        setNote(err instanceof Error ? err.message : "chat failed");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="pagehead">
        <span className="label label--accent">◈ SENTINEL CHAT</span>
        <h1 className="display">Talk to the plane.</h1>
        <p>
          Every turn goes through SENTINEL. Empty messages are rejected.
          Without Vertex / Gemini / Groq / Ollama you get a clear 503 — never a
          canned greeting from the SQL champion.
        </p>
      </div>
      <div className="glass-card" style={{ padding: 18, minHeight: 320, display: "flex", flexDirection: "column", gap: 12 }}>
        <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 10 }}>
          {messages.length === 0 && (
            <p className="label">no turns yet — ask about a run, a page, or a booking</p>
          )}
          {messages.map((m, i) => (
            <article key={i} className="panel" style={{ padding: 12 }}>
              <p className="label label--ink">{m.role}</p>
              <p style={{ margin: "6px 0 0", whiteSpace: "pre-wrap", fontSize: 14 }}>{m.content}</p>
            </article>
          ))}
        </div>
        {note && <p className="label label--accent">{note}</p>}
        <form onSubmit={send} style={{ display: "flex", gap: 10, alignItems: "end" }}>
          <div className="field" style={{ flex: 1, marginBottom: 0 }}>
            <input
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Message the control plane…"
            />
          </div>
          <button className="btn btn--accent" disabled={busy}>{busy ? "Sending…" : "Send"}</button>
        </form>
      </div>
    </>
  );
}
