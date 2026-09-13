"use client";

import { FormEvent, useEffect, useState } from "react";
import { api } from "@/lib/api";

type Item = {
  id: string; origin_module: string; kind: string; title: string; summary: string;
  created_at: string; used_by: string[]; score?: number;
};

const MODULES = ["medic", "operator", "shield", "vaani", "forge", "console"];

const STAMP_COLOR: Record<string, string> = {
  medic: "stamp--from-medic", operator: "stamp--from-operator", shield: "stamp--from-shield",
  vaani: "stamp--from-vaani", forge: "stamp--from-forge",
};

export default function LoomPage() {
  const [items, setItems] = useState<Item[]>([]);
  const [query, setQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [filterOrigin, setFilterOrigin] = useState("");
  const [title, setTitle] = useState("");
  const [summary, setSummary] = useState("");
  const [origin, setOrigin] = useState("shield");
  const [note, setNote] = useState<string | null>(null);

  async function load() {
    const q = filterOrigin ? `?origin=${filterOrigin}` : "";
    try {
      const i = await api<{ items: Item[] }>(`/api/loom/items${q}`);
      setItems(i.items);
    } catch (err) {
      setNote(err instanceof Error ? err.message : "LOOM failed");
    }
  }
  useEffect(() => { load(); }, [filterOrigin]);

  async function search(e: FormEvent) {
    e.preventDefault();
    if (query.trim().length < 2) { load(); return; }
    setSearching(true);
    try {
      const r = await api<{ hits: Item[] }>(`/api/loom/search?q=${encodeURIComponent(query)}`);
      setItems(r.hits);
    } catch (err) {
      setNote(err instanceof Error ? err.message : "search failed");
    }
    setSearching(false);
  }

  async function write(e: FormEvent) {
    e.preventDefault();
    try {
      await api("/api/loom/items", {
        method: "POST",
        headers: { "X-Module": origin },
        body: JSON.stringify({ kind: "note", title, summary, payload: {} }),
      });
      setTitle(""); setSummary("");
      load();
    } catch (err) {
      setNote(err instanceof Error ? err.message : "write failed");
    }
  }

  return (
    <>
      <div className="pagehead">
        <span className="label label--accent">◈ your agents&apos; shared memory</span>
        <h1 className="display">Memory.</h1>
        <p>
          Every incident MEDIC investigated, every attack SHIELD contained, every booking VAANI
          took, every note you wrote — kept here forever, so no agent ever asks you twice.
        </p>
        {note && <p className="label label--accent" style={{ marginTop: 10 }}>{note}</p>}
      </div>

      {/* ── Instrument panel ── */}
      <div className="instrument-grid">
        <div className="instrument glass-card">
          <p className="inst-label">total memories</p>
          <div className="inst-value">{items.length}</div>
        </div>
        {MODULES.slice(0, 5).map((m) => {
          const count = items.filter((i) => i.origin_module === m).length;
          return (
            <div key={m} className="instrument glass-card" onClick={() => setFilterOrigin(m)} style={{ cursor: "pointer" }}>
              <p className="inst-label">from {m}</p>
              <div className="inst-value">{count}</div>
            </div>
          );
        })}
      </div>

      {/* ── Search bar ── */}
      <div className="glass-card" style={{ padding: 18, marginBottom: 22 }}>
        <form onSubmit={search} style={{ display: "flex", gap: 10, alignItems: "end", flexWrap: "wrap" }}>
          <div className="field" style={{ marginBottom: 0, flex: 1, minWidth: 240 }}>
            <span className="label">semantic search (vector memory · MiniLM)</span>
            <input value={query} onChange={(e) => setQuery(e.target.value)}
                   placeholder="e.g. checkout incident, Ravi booking, SQL fixes" />
          </div>
          <button className="btn btn--accent" disabled={searching}>
            {searching ? "searching…" : "Search →"}
          </button>
          {query && (
            <button className="btn btn--ghost" type="button" onClick={() => { setQuery(""); load(); }}>clear</button>
          )}
        </form>
      </div>

      {/* ── Filter chips ── */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12, flexWrap: "wrap", gap: 10 }}>
        <p className="label label--ink" style={{ margin: 0 }}>
          SAVED MEMORIES — {items.length}{filterOrigin && ` · from ${filterOrigin}`}
        </p>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          <button className={`btn ${!filterOrigin ? "btn--accent" : "btn--ghost"}`} style={{ padding: "3px 10px", fontSize: 10 }}
                  onClick={() => setFilterOrigin("")}>ALL</button>
          {MODULES.map((m) => (
            <button key={m} className={`btn ${filterOrigin === m ? "btn--accent" : "btn--ghost"}`} style={{ padding: "3px 10px", fontSize: 10 }}
                    onClick={() => setFilterOrigin(m)}>{m}</button>
          ))}
        </div>
      </div>

      {/* ── Memory items ── */}
      <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 30 }}>
        {items.length === 0 && (
          <div className="empty">nothing saved yet — start a job in Fusion and whatever your agents
            learn will appear here automatically.</div>
        )}
        {items.map((item) => (
          <div key={item.id} className="glass-card" style={{ padding: 0, overflow: "hidden" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center",
                          padding: "10px 16px", borderBottom: "1px solid var(--line)", flexWrap: "wrap", gap: 6 }}>
              <span className="label">{item.kind} · {item.created_at.slice(0, 19)}</span>
              <span style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                {item.score != null && <span className="stamp stamp--phase">match {Math.round(item.score * 100)}%</span>}
                <span className={`stamp ${STAMP_COLOR[item.origin_module] ?? ""}`}>FROM {item.origin_module.toUpperCase()}</span>
                {item.used_by.slice(0, 3).map((m) => (
                  <span key={m} className="stamp stamp--used">USED BY {m.toUpperCase()}</span>
                ))}
              </span>
            </div>
            <div style={{ padding: "12px 16px" }}>
              <p style={{ margin: "0 0 4px", fontWeight: 600 }}>{item.title}</p>
              {item.summary && <p className="clamp3" style={{ margin: 0, fontSize: 13, color: "var(--ink-70)" }}>{item.summary}</p>}
            </div>
          </div>
        ))}
      </div>

      {/* ── Write a note ── */}
      <div className="glass-card" style={{ maxWidth: 720, padding: 20 }}>
        <p className="label label--ink" style={{ marginBottom: 10 }}>ADD A NOTE — every agent will see it</p>
        <form onSubmit={write} style={{ display: "flex", gap: 10, alignItems: "end", flexWrap: "wrap" }}>
          <div className="field" style={{ marginBottom: 0, width: 140 }}>
            <span className="label">saved as</span>
            <select value={origin} onChange={(e) => setOrigin(e.target.value)}
                    style={{ background: "var(--paper-raised)", border: "1px solid var(--line)", padding: "8px",
                             fontFamily: "var(--font-mono)", fontSize: 13 }}>
              {MODULES.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          </div>
          <div className="field" style={{ marginBottom: 0, flex: 1, minWidth: 200 }}>
            <span className="label">title</span>
            <input value={title} onChange={(e) => setTitle(e.target.value)} required placeholder="Incident on db-1" />
          </div>
          <div className="field" style={{ marginBottom: 0, flex: 1, minWidth: 200 }}>
            <span className="label">details</span>
            <input value={summary} onChange={(e) => setSummary(e.target.value)} placeholder="what your agents should know" />
          </div>
          <button className="btn">Write →</button>
        </form>
      </div>
    </>
  );
}
