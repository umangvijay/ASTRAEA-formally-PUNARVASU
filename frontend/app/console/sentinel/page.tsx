"use client";

import { useEffect, FormEvent, useState } from "react";
import { api, streamSSE } from "@/lib/api";

type Rule = { id: number; name: string; description: string; pattern: string; scope: string;
              action: string; enabled: boolean; global: boolean };
type Ev = { id: number; direction: string; rule_name: string; action: string; count: number;
            sample: string; latency_ms: number; at: string };
type Stats = { total_events: number; blocked: number; avg_scan_latency_ms: number;
               target_overhead_ms: number; quota: { tokens_used: number; quota: number; requests: number } };

export default function SentinelPage() {
  const [rules, setRules] = useState<Rule[]>([]);
  const [events, setEvents] = useState<Ev[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [pattern, setPattern] = useState("");
  const [name, setName] = useState("");
  const [live, setLive] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  useEffect(() => {
    const fail = (e: unknown) => setNote(e instanceof Error ? e.message : "SENTINEL API failed");
    api<{ rules: Rule[] }>("/api/sentinel/rules").then((r) => setRules(r.rules)).catch(fail);
    api<{ events: Ev[] }>("/api/sentinel/events").then((r) => setEvents(r.events)).catch(fail);
    api<Stats>("/api/sentinel/stats").then(setStats).catch(fail);
    const stop = streamSSE("/api/sentinel/stream", (ev) => {
      if (ev.kind === "guardrail" || ev.kind === "blocked") {
        setLive(true);
        setTimeout(() => setLive(false), 1500);
        const hits = (ev.hits as Ev[] | undefined) ?? [];
        if (hits.length) setEvents((list) => [...hits, ...list].slice(0, 60));
      }
    });
    return stop;
  }, []);

  async function toggle(rule: Rule) {
    const patched = await api<Rule>(`/api/sentinel/rules/${rule.id}`, {
      method: "PATCH", body: JSON.stringify({ enabled: !rule.enabled }),
    });
    setRules((list) => list.map((r) => (r.id === patched.id ? { ...r, ...patched } : r)));
    api<{ rules: Rule[] }>("/api/sentinel/rules").then((r) => setRules(r.rules)).catch(fail);
  }

  async function addRule(e: FormEvent) {
    e.preventDefault();
    const created = await api<Rule>("/api/sentinel/rules", {
      method: "POST",
      body: JSON.stringify({ name, pattern, scope: "both", action: "redact" }),
    });
    setRules((list) => [...list, created]);
    setName("");
    setPattern("");
  }

  const quotaPct = stats ? Math.min(100, (stats.quota.tokens_used / stats.quota.quota) * 100) : 0;

  return (
    <>
      <div className="pagehead">
        <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 6 }}>
          <span className={`dot ${live ? "dot--live" : "dot--olive"}`} />
          <span className="label label--accent">SENTINEL · LLM SECURITY GATEWAY</span>
        </div>
        <h1 className="display">Sentinel.</h1>
        <p>
          Layer 1 (regex / PII) always runs. ONNX and embeddings need weights
          (HF_TOKEN). LLM-as-judge only after L1 flags. Every model call still
          passes here. Rules are data, not code.
        </p>
        {note && <p className="label label--accent" style={{ marginTop: 10 }}>{note}</p>}
      </div>

      {/* ── Instrument panel ── */}
      <div className="instrument-grid">
        <div className="instrument glass-card">
          <p className="inst-label">guardrail events</p>
          <div className="inst-value">{stats?.total_events ?? "—"}</div>
        </div>
        <div className="instrument glass-card">
          <p className="inst-label">blocked</p>
          <div className="inst-value inst-value--accent">{stats?.blocked ?? "—"}</div>
        </div>
        <div className="instrument glass-card">
          <p className="inst-label">avg scan latency</p>
          <div className="inst-value">{stats?.avg_scan_latency_ms ?? "—"}<span style={{ fontSize: 12 }}> ms</span></div>
          <p className="inst-trend">target &lt; {stats?.target_overhead_ms ?? 120} ms</p>
        </div>
        <div className="instrument glass-card">
          <p className="inst-label">tokens this month</p>
          <div className="inst-value" style={{ fontSize: 16 }}>{stats?.quota.tokens_used?.toLocaleString() ?? "—"}</div>
          <div className="progress-track" style={{ marginTop: 8 }}>
            <div className={`progress-fill ${quotaPct > 80 ? "" : "progress-fill--olive"}`}
                 style={{ width: `${quotaPct}%` }} />
          </div>
          <p className="inst-trend">{stats?.quota.requests ?? 0} requests</p>
        </div>
      </div>

      {/* ── Detection layers ── */}
      <div className="glass-card" style={{ padding: 16, marginBottom: 22 }}>
        <p className="label label--ink" style={{ marginBottom: 8 }}>4-LAYER DETECTION PIPELINE</p>
        <div style={{ display: "flex", gap: 0, flexWrap: "wrap" }}>
          {[
            "L1: regex/heuristics (<5ms)",
            "L2: ONNX deberta-v3 (<20ms)",
            "L3: embedding similarity (<15ms)",
            "L4: LLM-judge (<80ms)",
          ].map((layer, i) => (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span className="stamp stamp--phase" style={{ transform: "none", fontSize: 9 }}>{layer}</span>
              {i < 3 && <span style={{ color: "var(--ink-30)", margin: "0 4px" }}>→</span>}
            </div>
          ))}
        </div>
      </div>

      {/* ── Rules editor ── */}
      <div className="glass-card" style={{ padding: 18, marginBottom: 22 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
          <p className="label label--ink" style={{ margin: 0 }}>RULES — editable, nothing hardcoded</p>
          <span className="label">{rules.length} rules</span>
        </div>
        <div style={{ maxHeight: 280, overflowY: "auto" }}>
          {rules.map((r) => (
            <div key={r.id} style={{ display: "flex", gap: 14, alignItems: "center", padding: "9px 0",
                                     borderBottom: "1px dotted var(--line)" }}>
              <button onClick={() => toggle(r)} className={`btn ${r.enabled ? "btn--accent" : "btn--ghost"}`}
                      style={{ padding: "3px 10px", fontSize: 10 }}>
                {r.enabled ? "ON" : "OFF"}
              </button>
              <span className="mono" style={{ fontSize: 12.5, minWidth: 180 }}>{r.name}</span>
              <span className="label">{r.scope}</span>
              <span className={`stamp ${r.action === "block" ? "" : r.action === "redact" ? "stamp--shared" : "stamp--phase"}`}>
                {r.action}
              </span>
              <span className="mono" style={{ fontSize: 11.5, color: "var(--ink-50)", flex: 1,
                                              overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {r.pattern}
              </span>
            </div>
          ))}
        </div>
        <form onSubmit={addRule} style={{ display: "flex", gap: 10, marginTop: 14, alignItems: "end", flexWrap: "wrap" }}>
          <div className="field" style={{ marginBottom: 0, minWidth: 180 }}>
            <span className="label">rule name</span>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="my-custom-leak" required />
          </div>
          <div className="field" style={{ marginBottom: 0, flex: 1, minWidth: 220 }}>
            <span className="label">regex pattern</span>
            <input value={pattern} onChange={(e) => setPattern(e.target.value)} placeholder="project-snowflake" required />
          </div>
          <button className="btn">Add rule →</button>
        </form>
      </div>

      {/* ── Live traffic ── */}
      <section>
        <p className="label label--ink" style={{ marginBottom: 12 }}>LIVE TRAFFIC — flagged events</p>
        <div className="glass-card sheet" style={{ maxHeight: 320, overflowY: "auto", padding: 0 }}>
          {events.length === 0 && <div className="empty" style={{ margin: 18 }}>quiet. flagged requests will appear here in real time.</div>}
          {events.map((e, i) => (
            <div key={`${e.id}-${i}`} className="timeline-item" style={{ padding: "8px 16px" }}>
              <span className={`stamp ${e.action === "block" ? "" : "stamp--shared"}`} style={{ minWidth: 60, textAlign: "center" }}>
                {e.action}
              </span>
              <span style={{ minWidth: 60, color: "var(--slate)", fontFamily: "var(--font-mono)", fontSize: 12 }}>{e.direction}</span>
              <span className="mono" style={{ minWidth: 180, fontSize: 12 }}>{e.rule_name}</span>
              <span className="t-detail" style={{ flex: 1 }}>{e.sample}</span>
              <span className="label">{e.latency_ms}ms</span>
            </div>
          ))}
        </div>
      </section>
    </>
  );
}
