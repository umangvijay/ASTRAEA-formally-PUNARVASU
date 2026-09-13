"use client";

import { FormEvent, useState } from "react";
import { ApiError, streamChat } from "@/lib/api";

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
    const next: Msg[] = [...messages, { role: "user", content }];
    setMessages([...next, { role: "assistant", content: "" }]);
    setText("");
    setBusy(true);
    setNote(null);
    let assembled = "";
    try {
      const meta = await streamChat(next, (delta) => {
        assembled += delta;
        setMessages([...next, { role: "assistant", content: assembled }]);
      });
      if (!assembled.trim()) {
        setNote("The model returned no content.");
        setMessages(next);
        return;
      }
      const who = meta.provider
        ? `${meta.provider}/${meta.model ?? ""}`
        : (meta.model ? meta.model : "sentinel");
      setMessages([...next, { role: "assistant", content: `${assembled}\n\n— ${who}` }]);
    } catch (err) {
      setMessages(next);
      if (err instanceof ApiError && err.status === 503) {
        setNote(err.message || "No general model is configured. Connect Vertex, Gemini, Groq or Ollama — the SQL champion is not used for chat.");
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
        <span className="label label--accent">SENTINEL · CHAT</span>
        <h1 className="display">Talk to the plane.</h1>
        <p>
          Every turn streams through SENTINEL as the model writes. Empty messages
          are rejected. Without Vertex / Gemini / Groq / Ollama you get a clear
          503 — never a canned greeting from the SQL champion.
        </p>
      </div>
      <div className="glass-card" style={{ padding: 18, minHeight: 320, display: "flex", flexDirection: "column", gap: 12 }}>
        <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 10 }}>
          {messages.length === 0 && (
            <p className="label">no turns yet — ask about a run, a page, or a booking</p>
          )}
          {messages.map((m, i) => (
            <article key={i} className={`chat-turn chat-turn--${m.role}`}>
              <p className="label label--ink">{m.role}</p>
              <p style={{ margin: "6px 0 0", whiteSpace: "pre-wrap", fontSize: 14 }}>{m.content || (busy && m.role === "assistant" ? "…" : "")}</p>
            </article>
          ))}
        </div>
        {note && <p className="label label--accent">{note}</p>}
        <form className="composer-row" onSubmit={send}>
          <div className="field" style={{ flex: 1, marginBottom: 0 }}>
            <input
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Message the control plane…"
            />
          </div>
          <button className="btn btn--accent" disabled={busy}>{busy ? "Streaming…" : "Send"}</button>
        </form>
      </div>
    </>
  );
}
