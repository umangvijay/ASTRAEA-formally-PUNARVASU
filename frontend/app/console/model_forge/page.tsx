"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";

type Overview = {
  champion: { capability: string; kind: string; score: number; model_path: string | null; scope?: string } | null;
  model_forge: { trained_model_available: boolean; path: string | null };
  eval_history: { id: number; variant: string; passed: number; total: number; score: number;
                  promoted: boolean; ran_at: string }[];
  eval_task_count: number;
};

export default function ModelForgePage() {
  const [data, setData] = useState<Overview | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  async function load() {
    api<Overview>("/api/forge/overview")
      .then(setData)
      .catch((err) => setNote(err instanceof Error ? err.message : "MODEL-FORGE API failed"));
  }
  useEffect(() => { load(); }, []);

  async function evaluate() {
    setBusy(true);
    setNote(null);
    try {
      const r = await api<{ score: number; passed: number; total: number; promoted: boolean; reason?: string }>(
        "/api/forge/eval",
        { method: "POST", body: JSON.stringify({ kind: "model", variant_name: `our-model-${Date.now() % 10000}` }) },
      );
      setNote(`our model: ${r.passed}/${r.total} = ${Math.round(r.score * 100)}% on the held-out SQL suite` +
        (r.promoted ? " — champion updated" : ` — champion holds (${r.reason ?? ""})`));
      await load();
    } catch (err) {
      setNote(err instanceof Error ? err.message : "eval failed");
    } finally {
      setBusy(false);
    }
  }

  const history = data?.eval_history ?? [];
  const maxScore = Math.max(1, ...history.map((h) => h.score));
  const latest = history.length ? history[history.length - 1] : null;

  return (
    <>
      <div className="pagehead">
        <span className="stamp">SOLO MODE</span>{" "}
        <span className="stamp stamp--phase">PHASE 6 LIVE</span>
        <h1 className="display">MODEL-FORGE.</h1>
        <p>
          Our own post-trained model (SFT + GRPO on verifiable SQL rewards), quantized and served
          behind SENTINEL. It answers every call the provider chain routes to it — measured, not claimed.
        </p>
      </div>

      <div className="grid" style={{ marginBottom: 26 }}>
        <div className="panel">
          <p className="label label--ink">serving status</p>
          <div style={{ marginTop: 8 }}>
            <div className="kv">
              <span className="k">weights</span>
              <span className="v">{data?.model_forge.trained_model_available ? "PROVISIONED" : "not trained yet"}</span>
            </div>
            <div className="kv"><span className="k">path</span><span className="v mono">{data?.model_forge.path ?? "—"}</span></div>
            <div className="kv"><span className="k">gateway</span><span className="v">behind SENTINEL, chain position: gemini → groq → ollama → <b>model_forge</b></span></div>
            <div className="kv"><span className="k">route</span><span className="v">model hint <span className="mono">pvu-sql</span> / <span className="mono">model_forge</span></span></div>
          </div>
        </div>
        <div className="panel">
          <p className="label label--ink">benchmark — held-out SQL suite ({data?.eval_task_count ?? 15} tasks)</p>
          <div style={{ marginTop: 8 }}>
            <div className="kv">
              <span className="k">latest score</span>
              <span className="v">{latest ? `${latest.passed}/${latest.total} (${Math.round(latest.score * 100)}%)` : "—"}</span>
            </div>
            <div className="kv">
              <span className="k">target</span>
              <span className="v">≥ 90%</span>
            </div>
          </div>
          <button className="btn btn--accent" style={{ marginTop: 12 }} disabled={busy || !data?.model_forge.trained_model_available} onClick={evaluate}>
            {busy ? "evaluating…" : "Re-run benchmark →"}
          </button>
          {note && <p className="label" style={{ marginTop: 10 }}>{note}</p>}
          {!data?.model_forge.trained_model_available && (
            <p className="label" style={{ marginTop: 10, lineHeight: 1.7 }}>
              train it: <span className="mono">python -m app.model_forge.train</span> (MLX LoRA on this machine)
            </p>
          )}
        </div>
      </div>

      <p className="label label--ink" style={{ marginBottom: 12 }}>EVAL HISTORY</p>
      <div className="panel sheet" style={{ marginBottom: 26 }}>
        {history.length === 0 ? (
          <div className="empty">no eval runs yet.</div>
        ) : (
          <div style={{ display: "flex", gap: 6, alignItems: "flex-end", height: 120, padding: "10px 4px" }}>
            {history.map((h) => (
              <div key={h.id} style={{ flex: 1, textAlign: "center" }} title={`${h.variant}: ${h.passed}/${h.total}`}>
                <div style={{
                  height: `${(h.score / maxScore) * 90}px`,
                  background: h.promoted ? "var(--accent)" : "var(--ink-30)",
                  border: "1px solid var(--ink)",
                }} />
                <span className="label">{h.score}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="footer-strip">
        <Link href="/console/forge" className="label">the self-evolution loop around this model lives in FORGE →</Link>
      </div>
    </>
  );
}
