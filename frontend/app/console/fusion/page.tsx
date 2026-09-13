"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { MODULES, api } from "@/lib/api";

type Sys = { active_profile: string; mode: string };
type Entry = {
  kind: string; module: string; title: string; detail: string;
  ts: string; link: string | null; attention?: boolean;
};
type Workflow = { id: string; name: string; needs_llm: boolean };

const KIND_STAMP: Record<string, string> = {
  run_started: "stamp--phase", run_resumed: "stamp--phase",
  run_completed: "stamp--shared", run_failed: "", run_interrupted: "",
  approval_required: "", approval_granted: "stamp--shared", approval_denied: "",
  anomaly: "", incident: "", loom: "stamp--used",
};

function ago(ts: string): string {
  const s = Math.max(0, (Date.now() - new Date(ts + "Z").getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return `${Math.floor(s / 86400)} d ago`;
}

export default function FusionPage() {
  const [sys, setSys] = useState<Sys | null>(null);
  const [timeline, setTimeline] = useState<Entry[]>([]);
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [goal, setGoal] = useState("");
  const [workflowId, setWorkflowId] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [jobPanelOpen, setJobPanelOpen] = useState(false);

  const load = useCallback(() => {
    api<{ timeline: Entry[] }>("/api/fusion/timeline?limit=40")
      .then((r) => setTimeline(r.timeline))
      .catch((err) => setNote(err instanceof Error ? err.message : "timeline failed"));
  }, []);

  useEffect(() => {
    api<Sys>("/api/modules").then(setSys).catch((err) => setNote(err instanceof Error ? err.message : "modules failed"));
    api<{ workflows: Workflow[] }>("/api/runs/workflows")
      .then((w) => {
        setWorkflows(w.workflows);
        const research = w.workflows.find((x) => x.name === "research-and-remember");
        if (research) setWorkflowId(research.id);
        else if (w.workflows[0]) setWorkflowId(w.workflows[0].id);
      })
      .catch((err) => setNote(err instanceof Error ? err.message : "workflows failed"));
    load();
    const t = setInterval(load, 8000);
    return () => clearInterval(t);
  }, [load]);

  async function launchRun(e: React.FormEvent) {
    e.preventDefault();
    setBusy("run"); setNote(null);
    try {
      const r = await api<{ id: string }>("/api/runs", {
        method: "POST", body: JSON.stringify({ goal, workflow_id: workflowId }),
      });
      setGoal("");
      setNote("job started — watch it appear in the timeline below");
      load();
      window.open(`/console/runs/${r.id}`, "_self");
    } catch (err) {
      setNote(err instanceof Error ? err.message : "failed to start");
    } finally { setBusy(null); }
  }

  async function quick(action: "chaos" | "attack") {
    setBusy(action); setNote(null);
    try {
      if (action === "chaos") {
        const r = await api<{ fault: string; service: string }>("/api/pulse/chaos", {
          method: "POST", body: JSON.stringify({}),
        });
        setNote(`fault "${r.fault}" injected into ${r.service} — MEDIC should catch it in seconds`);
      } else {
        const r = await api<{ scenario: string; events: number }>("/api/shield/lab/attack", {
          method: "POST", body: JSON.stringify({}),
        });
        setNote(`test attack "${r.scenario}" fired (${r.events} events) — SHIELD should raise an incident`);
      }
      setTimeout(load, 6000);
    } catch (err) {
      setNote(err instanceof Error ? err.message : "failed");
    } finally { setBusy(null); }
  }

  const attention = timeline.filter((e) => e.attention);
  const rest = timeline.filter((e) => !e.attention);

  return (
    <>
      <div className="pagehead">
        <span className="label label--accent">◈ mission control — start work, then watch it happen</span>
        <h1 className="display">Fusion.</h1>
        <p>
          Start any job, then follow everything your agents do in one live feed —
          and everything waiting for your decision.
        </p>
      </div>

      {/* ── Compact action toolbar ── */}
      <div style={{ display: "flex", gap: 10, marginBottom: 20, flexWrap: "wrap", alignItems: "center" }}>
        <button className="btn btn--accent" onClick={() => setJobPanelOpen(!jobPanelOpen)}>
          {jobPanelOpen ? "▾ Close" : "▸ Start a job"}
        </button>
        <button className="btn" disabled={busy === "chaos"} onClick={() => quick("chaos")}>
          {busy === "chaos" ? "injecting…" : "⚡ Break a service"}
        </button>
        <button className="btn" disabled={busy === "attack"} onClick={() => quick("attack")}>
          {busy === "attack" ? "firing…" : "⚡ Simulate attack"}
        </button>
        <Link href="/console/runs" className="label" style={{ marginLeft: "auto" }}>all jobs →</Link>
      </div>

      {/* ── Collapsible job form ── */}
      <div className={`collapsible-content ${jobPanelOpen ? "open" : ""}`} style={{ marginBottom: jobPanelOpen ? 20 : 0 }}>
        <div className="glass-card" style={{ padding: 20 }}>
          <form onSubmit={launchRun} style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "end" }}>
            <div className="field" style={{ marginBottom: 0, flex: 2, minWidth: 240 }}>
              <span className="label">what do you want done?</span>
              <input value={goal} onChange={(e) => setGoal(e.target.value)}
                     placeholder="e.g. research how isolation forests work and save the findings"
                     required minLength={3} maxLength={2000} />
            </div>
            <div className="field" style={{ marginBottom: 0, flex: 1, minWidth: 200 }}>
              <span className="label">recipe</span>
              <select value={workflowId} onChange={(e) => setWorkflowId(e.target.value)}
                      style={{ background: "var(--paper-raised)", border: "1px solid var(--line)",
                               padding: "8px", fontFamily: "var(--font-mono)", fontSize: 13 }}>
                {workflows.map((w) => (
                  <option key={w.id} value={w.id}>{w.name}{w.needs_llm ? " · needs AI" : " · no AI needed"}</option>
                ))}
              </select>
            </div>
            <button className="btn btn--accent" disabled={busy === "run"}>
              {busy === "run" ? "starting…" : "Start →"}
            </button>
          </form>
        </div>
      </div>

      {note && <div className="glass-card" style={{ padding: "10px 16px", marginBottom: 16 }}><span className="label">{note}</span></div>}

      {/* ── Attention items — highest visual priority ── */}
      {attention.length > 0 && (
        <section style={{ marginBottom: 22 }}>
          <p className="label label--accent" style={{ marginBottom: 10 }}>
            ⚑ NEEDS YOUR DECISION — {attention.length}
          </p>
          {attention.map((e, i) => (
            <div key={`a-${i}`} className="glass-card" style={{
              marginBottom: 8, borderColor: "var(--accent)",
              display: "flex", gap: 14, alignItems: "center",
              flexWrap: "wrap", padding: "14px 18px",
              animation: `glowPulse 3s ease-in-out infinite`,
            }}>
              <span className="stamp">{e.module.toUpperCase()}</span>
              <div style={{ flex: 1, minWidth: 220 }}>
                <p style={{ margin: 0, fontWeight: 600, fontSize: 13.5 }}>{e.title}</p>
                {e.detail && <p style={{ margin: "2px 0 0", fontSize: 12.5, color: "var(--ink-70)" }}>{e.detail}</p>}
              </div>
              {e.link && <Link href={e.link} className="btn btn--accent">Review →</Link>}
            </div>
          ))}
        </section>
      )}

      {/* ── Live timeline ── */}
      <section style={{ marginBottom: 30 }}>
        <p className="label label--ink" style={{ marginBottom: 10 }}>LIVE TIMELINE</p>
        <div className="glass-card sheet" style={{ maxHeight: 480, overflowY: "auto", padding: 0 }}>
          {rest.length === 0 && attention.length === 0 && (
            <div className="empty" style={{ margin: 18 }}>
              quiet. start an agent (Agents menu above), inject a fault in MEDIC or fire a
              test attack in SHIELD — everything shows up here.
            </div>
          )}
          {rest.map((e, i) => (
            <div key={i} className="timeline-item" style={{ padding: "10px 18px" }}>
              <span className="t-ts" title={e.ts}>{ago(e.ts)}</span>
              <span style={{ minWidth: 88 }}>
                <span className={`stamp ${KIND_STAMP[e.kind] ?? ""}`}>{e.module.toUpperCase()}</span>
              </span>
              <div className="t-body">
                {e.link ? (
                  <Link href={e.link}><p className="t-title" style={{ textDecoration: "underline" }}>{e.title}</p></Link>
                ) : (
                  <p className="t-title">{e.title}</p>
                )}
                {e.detail && <p className="t-detail">{e.detail}</p>}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── Crew cards — compact ── */}
      <section>
        <p className="label label--ink" style={{ marginBottom: 10 }}>THE CREW — click any agent to open its workbench</p>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          {MODULES.map((m) => (
            <Link key={m.codename} href={`/console/${m.codename}`}
                  className="glass-card" style={{ flex: "1 1 180px", padding: "12px 16px", textDecoration: "none" }}>
              <h3 className="display" style={{ margin: 0, fontSize: 16 }}>{m.name}</h3>
              <p className="clamp2" style={{ fontSize: 11.5, color: "var(--ink-70)", margin: "4px 0 0" }}>{m.title}</p>
            </Link>
          ))}
        </div>
      </section>
    </>
  );
}
