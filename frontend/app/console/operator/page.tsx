"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";

type ResearchPage = {
  url: string;
  title?: string;
  snippet?: string;
  text?: string;
  status?: number;
  ok?: boolean;
  error?: string;
};

type ResearchOut = {
  query: string;
  engine: string;
  hits: { title: string; url: string; snippet: string }[];
  pages: ResearchPage[];
  synthesis?: { text?: string | null; provider?: string; model?: string; degraded?: string };
};

type Bench = {
  run: boolean;
  summary: {
    tasks: number; success: number; success_rate: number; gate_target: number;
    total_replans: number; ran_at: string;
    results: { name: string; status: string; steps: number; replans: number; duration_s: number; reason?: string }[];
  } | null;
};

const STATUS_STAMP: Record<string, string> = {
  success: "stamp--shared", gave_up: "", stalled: "stamp--phase", error: "",
};

export default function OperatorPage() {
  const [bench, setBench] = useState<Bench | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [goal, setGoal] = useState("");
  const [taskUrl, setTaskUrl] = useState("");
  const [successUrl, setSuccessUrl] = useState("");
  const [researchQ, setResearchQ] = useState("");
  const [research, setResearch] = useState<ResearchOut | null>(null);
  const [researching, setResearching] = useState(false);

  async function runResearch(e: React.FormEvent) {
    e.preventDefault();
    setResearching(true);
    setNote(null);
    try {
      const pack = await api<ResearchOut>("/api/operator/research", {
        method: "POST",
        body: JSON.stringify({ query: researchQ, max_results: 4, synthesize: true }),
      });
      setResearch(pack);
    } catch (err) {
      setNote(err instanceof Error ? err.message : "research failed");
    } finally { setResearching(false); }
  }

  async function runTask(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setNote(null);
    try {
      const r = await api<{ run_id: string }>("/api/operator/task", {
        method: "POST",
        body: JSON.stringify({
          goal, url: taskUrl,
          ...(successUrl ? { success_url_contains: successUrl } : {}),
        }),
      });
      window.location.href = `/console/runs/${r.run_id}`;
    } catch (err) {
      setNote(err instanceof Error ? err.message : "failed");
    } finally { setBusy(false); }
  }

  async function load() {
    api<Bench>("/api/operator/benchmark")
      .then(setBench)
      .catch((err) => setNote(err instanceof Error ? err.message : "benchmark failed"));
  }

  useEffect(() => { load(); }, []);

  const s = bench?.summary;
  const successRate = s?.success_rate != null ? Math.round(s.success_rate * 100) : null;

  return (
    <>
      <div className="pagehead">
        <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 6 }}>
          <span className="label label--accent">OPERATOR · VISION COMPUTER-USE</span>
          <span className="stamp stamp--phase">PHASE 3</span>
        </div>
        <h1 className="display">OPERATOR.</h1>
        <p>
          Live search + fetch first (real HTML per URL). Default grounding is DOM,
          not OmniParser. No OSWorld VM on this box. Login walls stay walls —
          research reads the public web instead of inventing a click-failure.
        </p>
      </div>

      <div className="glass-card" style={{ padding: 20, marginBottom: 22 }}>
        <p className="label label--accent" style={{ margin: "0 0 12px" }}>LIVE WEB RESEARCH</p>
        <form onSubmit={runResearch} style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "end" }}>
          <div className="field" style={{ marginBottom: 0, flex: 1, minWidth: 260 }}>
            <span className="label">query — searched and fetched live</span>
            <input value={researchQ} onChange={(e) => setResearchQ(e.target.value)}
                   placeholder="what is Astraea the constellation" required minLength={2} />
          </div>
          <button className="btn btn--accent" disabled={researching}>
            {researching ? "Fetching…" : "Research →"}
          </button>
        </form>
        {note && <p className="label" style={{ marginTop: 10 }}>{note}</p>}
        {research && (
          <div style={{ marginTop: 16 }}>
            <p className="label" style={{ marginBottom: 8 }}>
              engine {research.engine} · {research.pages.length} pages · each excerpt is from that URL
            </p>
            {research.synthesis?.text && (
              <div className="glass-card" style={{ padding: 14, marginBottom: 12 }}>
                <p className="label label--ink">SYNTHESIS · {research.synthesis.provider} / {research.synthesis.model}</p>
                <p style={{ margin: "6px 0 0", fontSize: 14, whiteSpace: "pre-wrap" }}>{research.synthesis.text}</p>
              </div>
            )}
            {research.synthesis?.degraded && (
              <div className="glass-card" style={{ padding: 14, marginBottom: 12 }}>
                <p className="label label--accent">BRAIN OFFLINE</p>
                <p style={{ margin: "6px 0 0", fontSize: 13.5, color: "var(--ink-70)" }}>
                  The pages below are live HTML from the search. A summary needs
                  Vertex, Gemini, Groq or Ollama — the SQL champion is not used here.
                </p>
              </div>
            )}
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {research.pages.map((p) => (
                <article key={p.url} className="glass-card" style={{ padding: 14 }}>
                  <a href={p.url} target="_blank" rel="noreferrer" className="mono" style={{ fontSize: 12, color: "var(--accent)" }}>
                    {p.url}
                  </a>
                  <h3 style={{ margin: "6px 0 4px", fontSize: 16 }}>{p.title || p.url}</h3>
                  <p style={{ margin: 0, fontSize: 13, color: "var(--ink-70)" }}>
                    {(p.text || p.snippet || p.error || "no extract").slice(0, 420)}
                  </p>
                  <p className="label" style={{ marginTop: 8 }}>
                    {p.ok ? `http ${p.status ?? 200}` : "fetch failed"} · {(p.text || "").length} chars
                  </p>
                </article>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* ── Instrument panel ── */}
      {s && (
        <div className="instrument-grid">
          <div className="instrument glass-card">
            <p className="inst-label">tasks</p>
            <div className="inst-value">{s.tasks}</div>
          </div>
          <div className="instrument glass-card">
            <p className="inst-label">success</p>
            <div className="inst-value inst-value--accent">{s.success}</div>
          </div>
          <div className="instrument glass-card">
            <p className="inst-label">success rate</p>
            <div className="inst-value">{successRate != null ? `${successRate}%` : "—"}</div>
            {successRate != null && (
              <div className="progress-track" style={{ marginTop: 8 }}>
                <div className={`progress-fill ${successRate >= 50 ? "progress-fill--olive" : "progress-fill--amber"}`}
                     style={{ width: `${successRate}%` }} />
              </div>
            )}
            <p className="inst-trend">gate target: {s.gate_target ? Math.round(s.gate_target * 100) : 50}%</p>
          </div>
          <div className="instrument glass-card">
            <p className="inst-label">self-corrections</p>
            <div className="inst-value">{s.total_replans}</div>
          </div>
          <div className="instrument glass-card">
            <p className="inst-label">last run</p>
            <div className="inst-value" style={{ fontSize: 13 }}>{s.ran_at?.slice(0, 16) ?? "—"}</div>
          </div>
        </div>
      )}

      {/* ── Task form ── */}
      <div className="glass-card" style={{ padding: 20, marginBottom: 22 }}>
        <p className="label label--accent" style={{ margin: "0 0 12px" }}>RUN A BROWSER TASK</p>
        <form onSubmit={runTask} style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "end" }}>
          <div className="field" style={{ marginBottom: 0, flex: 1, minWidth: 220 }}>
            <span className="label">goal</span>
            <input value={goal} onChange={(e) => setGoal(e.target.value)}
                   placeholder="open the wikipedia page for Grace Hopper" required minLength={3} />
          </div>
          <div className="field" style={{ marginBottom: 0, flex: 1, minWidth: 220 }}>
            <span className="label">start url</span>
            <input value={taskUrl} onChange={(e) => setTaskUrl(e.target.value)}
                   placeholder="https://en.wikipedia.org" required />
          </div>
          <div className="field" style={{ marginBottom: 0, flex: 1, minWidth: 200 }}>
            <span className="label">success when URL contains (optional)</span>
            <input value={successUrl} onChange={(e) => setSuccessUrl(e.target.value)}
                   placeholder="e.g. Grace_Hopper" />
          </div>
          <button className="btn btn--accent" disabled={busy}>Execute →</button>
        </form>
        {note && <p className="label" style={{ marginTop: 10 }}>{note}</p>}
      </div>

      {/* ── Action ladder ── */}
      <div className="glass-card" style={{ padding: 16, marginBottom: 22 }}>
        <p className="label label--ink" style={{ marginBottom: 8 }}>ACTION LADDER</p>
        <div style={{ display: "flex", gap: 0, flexWrap: "wrap" }}>
          {["ground · DOM + SoM", "decide · vision chain", "act · isolated browser", "verify · pixel diff", "remember · trajectory → LOOM"].map((step, i) => (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span className="stamp" style={{ transform: "none", fontSize: 9 }}>{i + 1}</span>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--ink-70)", whiteSpace: "nowrap" }}>{step}</span>
              {i < 4 && <span style={{ color: "var(--ink-30)", margin: "0 8px" }}>→</span>}
            </div>
          ))}
        </div>
      </div>

      {/* ── Benchmark results ── */}
      {!bench || !bench.run ? (
        <div className="empty" style={{ marginBottom: 26 }}>
          no suite run yet — execute <span className="mono">python -m app.operator.suite</span> to
          score OPERATOR on the 20-task web suite.
        </div>
      ) : (
        <section>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
            <p className="label label--ink" style={{ margin: 0 }}>TASK RESULTS</p>
            <button className="btn btn--ghost" onClick={load} style={{ padding: "3px 10px", fontSize: 10 }}>Refresh</button>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 26 }}>
            {(s?.results ?? []).map((r) => (
              <div key={r.name} className="glass-card" style={{ padding: "10px 16px", display: "flex", gap: 14, alignItems: "center" }}>
                <span className={`stamp ${STATUS_STAMP[r.status] ?? ""}`} style={{ minWidth: 76, textAlign: "center" }}>
                  {r.status}
                </span>
                <span className="mono" style={{ fontSize: 13, flex: 1 }}>{r.name}</span>
                <span className="label">{r.steps} steps · {r.replans} replans · {r.duration_s}s</span>
              </div>
            ))}
          </div>
        </section>
      )}

      <div className="footer-strip">
        <Link href="/console/runs" className="label">see all durable runs →</Link>
      </div>
    </>
  );
}