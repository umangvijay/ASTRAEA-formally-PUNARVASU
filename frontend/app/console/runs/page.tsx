"use client";

import { useEffect, FormEvent, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";

type Run = { id: string; goal: string; status: string; origin_module: string; created_at: string };
type Workflow = { id: string; name: string; description: string; needs_llm: boolean };

const STATUS: Record<string, { label: string; cls: string; hint: string }> = {
  running: { label: "RUNNING", cls: "st-run", hint: "working right now" },
  awaiting_approval: { label: "WAITING FOR YOU", cls: "st-wait", hint: "needs your decision" },
  completed: { label: "DONE", cls: "st-done", hint: "finished successfully" },
  failed: { label: "FAILED", cls: "st-fail", hint: "stopped with an error" },
  interrupted: { label: "PAUSED", cls: "st-wait", hint: "stopped — you can resume it" },
  queued: { label: "QUEUED", cls: "st-wait", hint: "about to start" },
};

export default function RunsPage() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [goal, setGoal] = useState("");
  const [workflowId, setWorkflowId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      const r = await api<{ runs: Run[] }>("/api/runs");
      setRuns(r.runs);
    } catch (err) {
      setError(err instanceof Error ? err.message : "runs failed");
    }
  }

  useEffect(() => {
    api<{ workflows: Workflow[] }>("/api/runs/workflows")
      .then((w) => {
        setWorkflows(w.workflows);
        if (w.workflows[0]) setWorkflowId(w.workflows[0].id);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "workflows failed"));
    load();
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, []);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const run = await api<Run>("/api/runs", {
        method: "POST",
        body: JSON.stringify({ goal, workflow_id: workflowId }),
      });
      window.location.href = `/console/runs/${run.id}`;
    } catch (err) {
      setError(err instanceof Error ? err.message : "failed");
    } finally {
      setBusy(false);
    }
  }

  const waiting = runs.filter((r) => r.status === "awaiting_approval");

  return (
    <>
      <div className="pagehead">
        <span className="label">everything your agents do, recorded forever</span>
        <h1 className="display">Runs.</h1>
        <p>
          A run is a job an agent does for you — step by step, saved as it goes.
          If anything crashes it picks up where it stopped, and before anything
          risky happens, it asks you first.
        </p>
      </div>

      {waiting.length > 0 && (
        <section style={{ marginBottom: 22 }}>
          {waiting.map((r) => (
            <div key={r.id} className="panel" style={{ borderColor: "var(--accent)", marginBottom: 8,
                                                       display: "flex", gap: 14, alignItems: "center",
                                                       flexWrap: "wrap", padding: "12px 16px" }}>
              <span className="stamp">⚑ {r.origin_module.toUpperCase()}</span>
              <p style={{ flex: 1, minWidth: 220, margin: 0, fontWeight: 600, fontSize: 13.5 }}>
                {r.goal}
                <span className="label" style={{ marginLeft: 10 }}>waiting for your decision</span>
              </p>
              <Link href={`/console/runs/${r.id}`} className="btn btn--accent">Decide →</Link>
            </div>
          ))}
        </section>
      )}

      <div className="panel" style={{ marginBottom: 26 }}>
        <p className="label label--ink">start a job — pick a recipe, describe what you want in plain words</p>
        <form onSubmit={submit} style={{ marginTop: 12 }}>
          <div className="field">
            <span className="label">what do you want done?</span>
            <input
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
              placeholder="e.g. take a snapshot of this machine and remember it"
              required
              minLength={3}
              maxLength={2000}
            />
          </div>
          <div className="field">
            <span className="label">recipe (how the agent should work)</span>
            <select
              value={workflowId}
              onChange={(e) => setWorkflowId(e.target.value)}
              style={{ background: "var(--paper-raised)", border: "1px solid var(--line)",
                       padding: "8px", fontFamily: "var(--font-mono)", fontSize: 13 }}
            >
              {workflows.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}{w.needs_llm ? " — needs an AI model" : " — no AI model needed"}
                </option>
              ))}
            </select>
          </div>
          <p className="label" style={{ marginBottom: 12, lineHeight: 1.7 }}>
            {workflows.find((w) => w.id === workflowId)?.description}
          </p>
          {error && <div className="err">✕ {error}</div>}
          <button className="btn btn--accent" disabled={busy || !workflowId}>
            {busy ? "starting…" : "Start the job →"}
          </button>
        </form>
      </div>

      <p className="label label--ink" style={{ marginBottom: 12 }}>HISTORY — newest first</p>
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {runs.length === 0 && (
          <div className="empty">no jobs yet — start one above and watch it work live.</div>
        )}
        {runs.map((r) => {
          const st = STATUS[r.status] ?? { label: r.status.toUpperCase(), cls: "st-wait", hint: "" };
          return (
            <Link key={r.id} href={`/console/runs/${r.id}`} className="panel module-card" style={{ padding: 0 }}>
              <div className="head">
                <span className="label">{r.origin_module} · {r.created_at.slice(0, 16).replace("T", " ")}</span>
                <span className={`stamp status-chip ${st.cls}`} title={st.hint}>{st.label}</span>
              </div>
              <div className="body" style={{ padding: "12px 18px" }}>
                <p style={{ margin: 0, fontFamily: "var(--font-mono)", fontSize: 13.5 }}>{r.goal}</p>
              </div>
            </Link>
          );
        })}
      </div>
    </>
  );
}
