"use client";

import { FormEvent, useState } from "react";
import { ApiError, streamChat } from "@/lib/api";

type Msg = { role: "user" | "assistant"; content: string };

const MODELS = [
  {
    id: "gemini-3.8-flash",
    name: "Gemini 3.8 Flash",
    description: "Fast default model",
  },
  {
    id: "gemini-3.1-pro-preview",
    name: "Gemini 3.1 Pro",
    description: "Advanced reasoning",
  },
] as const;

export default function ChatPage() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [model, setModel] = useState("gemini-3.8-flash");
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
      const meta = await streamChat(
        next,
        (delta) => {
          assembled += delta;
          setMessages([
            ...next,
            { role: "assistant", content: assembled },
          ]);
        },
        model,
      );

      if (!assembled.trim()) {
        setNote("The model returned no content.");
        setMessages(next);
        return;
      }

      const who = meta.provider
        ? `${meta.provider}/${meta.model ?? model}`
        : meta.model ?? model;

      setMessages([
        ...next,
        {
          role: "assistant",
          content: `${assembled}\n\n— ${who}`,
        },
      ]);
    } catch (err) {
      setMessages(next);

      if (err instanceof ApiError && err.status === 503) {
        setNote(err.message || "Vertex AI model unavailable.");
      } else {
        setNote(
          err instanceof Error ? err.message : "chat failed",
        );
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="pagehead">
        <span className="label label--accent">
          SENTINEL · CHAT
        </span>

        <h1 className="display">
          Talk to the plane.
        </h1>

        <p>
          Every turn streams through SENTINEL and Vertex AI.
          Choose Gemini 3.8 Flash or Gemini 3.1 Pro.
        </p>
      </div>

      <div
        className="glass-card"
        style={{
          padding: 18,
          minHeight: 320,
          display: "flex",
          flexDirection: "column",
          gap: 12,
        }}
      >
        {/* Model selector */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            flexWrap: "wrap",
          }}
        >
          <span className="label">
            MODEL
          </span>

          <div
            className="field"
            style={{
              marginBottom: 0,
              minWidth: 260,
            }}
          >
            <select
              value={model}
              onChange={(e) => setModel(e.target.value)}
              disabled={busy}
              aria-label="Select Gemini model"
              style={{
                width: "100%",
                margin: 0,
                background: "transparent",
                border: 0,
                outline: 0,
              }}
            >
              {MODELS.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name} — {m.description}
                </option>
              ))}
            </select>
          </div>

          <span className="label label--accent">
            Vertex AI
          </span>
        </div>

        {/* Messages */}
        <div
          style={{
            flex: 1,
            display: "flex",
            flexDirection: "column",
            gap: 10,
          }}
        >
          {messages.length === 0 && (
            <p className="label">
              no turns yet — choose a model and ask a question
            </p>
          )}

          {messages.map((m, i) => (
            <article
              key={i}
              className={`chat-turn chat-turn--${m.role}`}
            >
              <p className="label label--ink">
                {m.role}
              </p>

              <p
                style={{
                  margin: "6px 0 0",
                  whiteSpace: "pre-wrap",
                  fontSize: 14,
                }}
              >
                {m.content ||
                  (busy && m.role === "assistant"
                    ? "…"
                    : "")}
              </p>
            </article>
          ))}
        </div>

        {note && (
          <p className="label label--accent">
            {note}
          </p>
        )}

        {/* Composer */}
        <form
          className="composer-row"
          onSubmit={send}
        >
          <div
            className="field"
            style={{
              flex: 1,
              marginBottom: 0,
            }}
          >
            <input
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Message the control plane…"
            />
          </div>

          <button
            className="btn btn--accent"
            disabled={busy}
          >
            {busy ? "Streaming…" : "Send"}
          </button>
        </form>
      </div>
    </>
  );
}
