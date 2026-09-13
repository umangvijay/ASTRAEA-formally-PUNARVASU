"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type Overview = {
  champion: { capability: string; kind: string; score: number; model_path: string | null } | null;
  model_forge: { trained_model_available: boolean; path: string | null };
  candidates: { id: number; source: string; kind: string; status: string; reason: string;
                score_before: number | null; score_after: number | null }[];
  eval_history: { id: number; variant: string; passed: number; total: number; score: number;
                  promoted: boolean; ran_at: string }[];
  failure_mining: { clusters: number; proposals: { cluster: string; occurrences: number;
                  sample_error: string; change: { suggestion: string } }[] };
  eval_task_count: number;
};

export default function ForgePage() {
  const [data, setData] = useState<Overview | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  async function load() {
    api<Overview>("/api/forge/overview")
      .then(setData)
      .catch((err) => setNote(err instanceof Error ? err.message : "FORGE API failed"));
  }
  useEffect(() => { load(); }, []);

  async function evaluate(kind: "prompt-variant" | "model") {
    setBusy(true);
    setNote(null);
    try {
      const r = await api<{ score: number; promoted: boolean; reason?: string }>("/api/forge/eval", {
        method: "POST",
        body: JSON.stringify({ kind, variant_name: `${kind}-${Date.now() % 10000}` }),
      });
      setNote(r.promoted
        ? `PROMOTED — new champion score ${r.score} (git committed)`
        : `rejected — ${r.reason ?? `score ${r.score} not better than champion`}`);
      await load();
    } catch (err) {
      setNote(err instanceof Error ? err.message : "eval failed");
    } finally {
      setBusy(false);
    }
  }

  const maxScore = Math.max(1, ...(data?.eval_history.map((h) => h.score) ?? [1]));

  return (
    <>
      <div className="pagehead">
        <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 6 }}>
          <span className="label label--accent">FORGE · SELF-EVOLVING ENGINE</span>
          <span className="stamp stamp--phase">PHASE 6</span>
        </div>
        <h1 className="display">FORGE.</h1>
        <p>
          SQL-prompt eval loop on this box — not a 50-task OSWorld chart.
          Promotion only if the measured score beats the champion.
        </p>
      </div>

      {/* ── Instrument panel ── */}
      <div className="instrument-grid">
        <div className="instrument glass-card">
          <p className="inst-label">champion</p>
          <div className="inst-value" style={{ fontSize: 14 }}>{data?.champion?.capability ?? "—"}</div>
          <p className="inst-trend">{data?.champion?.kind ?? "—"}</p>
        </div>
        <div className="instrument glass-card">
          <p className="inst-label">champion score</p>
          <div className="inst-value inst-value--accent">{data?.champion?.score ?? "—"}</div>
        </div>
        <div className="instrument glass-card">
          <p className="inst-label">eval tasks</p>
          <div className="inst-value">{data?.eval_task_count ?? "—"}</div>
        </div>
        <div className="instrument glass-card">
          <p className="inst-label">our model</p>
          <div className="inst-value" style={{ fontSize: 13 }}>
            {data?.model_forge.trained_model_available ? "SERVING" : "not trained"}
          </div>
          <p className="inst-trend">{data?.model_forge.trained_model_available ? "behind SENTINEL" : "run train script"}</p>
        </div>
        <div className="instrument glass-card">
          <p className="inst-label">failure clusters</p>
          <div className="inst-value">{data?.failure_mining.clusters ?? 0}</div>
        </div>
      </div>

      {/* ── Eval controls ── */}
      <div className="glass-card" style={{ padding: 18, marginBottom: 22 }}>
        <p className="label label--accent" style={{ margin: "0 0 12px" }}>EVALUATE A CANDIDATE (gate: only better wins)</p>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
          <button className="btn btn--accent" disabled={busy} onClick={() => evaluate("prompt-variant")}>
            Eval prompt variant →
          </button>
          <button className="btn" disabled={busy || !data?.model_forge.trained_model_available}
                  onClick={() => evaluate("model")}>
            Eval our trained model →
          </button>
        </div>
        {note && <p className="label" style={{ marginTop: 10 }}>{note}</p>}
        {!data?.model_forge.trained_model_available && (
          <p className="label" style={{ marginTop: 10, lineHeight: 1.7 }}>
            train: <span className="mono">python -m app.model_forge.train</span> (MLX LoRA on this machine; Colab SFT+GRPO for scale)
          </p>
        )}
      </div>

      {/* ── Improvement chart ── */}
      <section style={{ marginBottom: 26 }}>
        <p className="label label--ink" style={{ marginBottom: 12 }}>EVAL HISTORY — THE IMPROVEMENT CHART</p>
        <div className="glass-card sheet" style={{ padding: "16px 12px" }}>
          {!data || data.eval_history.length === 0 ? (
            <div className="empty">no eval runs yet — every run appends a bar; promotion only on measured improvement.</div>
          ) : (
            <div style={{ display: "flex", gap: 6, alignItems: "flex-end", height: 140 }}>
              {data.eval_history.map((h) => (
                <div key={h.id} style={{ flex: 1, textAlign: "center", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "flex-end" }}
                     title={`${h.variant}: ${h.passed}/${h.total}`}>
                  <div style={{
                    width: "100%", maxWidth: 40,
                    height: `${(h.score / maxScore) * 110}px`,
                    background: h.promoted
                      ? "linear-gradient(180deg, var(--accent), color-mix(in srgb, var(--accent) 60%, transparent))"
                      : "var(--ink-12)",
                    border: "1px solid var(--line-strong)",
                    transition: "height 0.5s var(--ease)",
                  }} />
                  <span className="label" style={{ marginTop: 4 }}>{h.score}</span>
                  <span className="label" style={{ fontSize: 8 }}>{h.promoted ? "★" : ""}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </section>

      {/* ── Two columns: failure mining + candidates ── */}
      <div className="grid">
        <div className="glass-card" style={{ padding: 18 }}>
          <p className="label label--ink" style={{ marginBottom: 8 }}>FAILURE MINING — real run_events</p>
          {(data?.failure_mining.proposals ?? []).length === 0 && (
            <div className="empty">no failure clusters — the agents are behaving.</div>
          )}
          {(data?.failure_mining.proposals ?? []).map((p, i) => (
            <div key={i} style={{ padding: "8px 0", borderBottom: "1px dotted var(--line)" }}>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span className="mono" style={{ fontSize: 12 }}>{p.cluster}</span>
                <span className="stamp stamp--phase">×{p.occurrences}</span>
              </div>
              <p className="label" style={{ margin: "4px 0 0" }}>→ {p.change.suggestion}</p>
            </div>
          ))}
        </div>
        <div className="glass-card" style={{ padding: 18 }}>
          <p className="label label--ink" style={{ marginBottom: 8 }}>CANDIDATES LEDGER</p>
          {(data?.candidates ?? []).length === 0 && (
            <div className="empty">no candidates yet.</div>
          )}
          {(data?.candidates ?? []).slice(0, 8).map((c) => (
            <div key={c.id} style={{ padding: "8px 0", borderBottom: "1px dotted var(--line)" }}>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <span className={`stamp ${c.status === "promoted" ? "stamp--shared" : "stamp--phase"}`}>{c.status}</span>
                <span className="label">{c.source} · {c.kind}</span>
              </div>
              <p className="label" style={{ margin: "4px 0 0" }}>
                {c.score_before ?? "—"} → {c.score_after ?? "—"}
              </p>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
