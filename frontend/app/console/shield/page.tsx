"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, streamSSE } from "@/lib/api";

type Incident = {
  id: number; host: string; attacker_ip: string | null; severity: string;
  techniques: { id: string; name: string; tactic: string }[];
  narrative: string; status: string; run_id: string | null; detected_at: string;
  containment: Record<string, unknown> | null;
  attack_graph: { nodes?: { kind: string; label: string }[]; edges?: { src: string; dst: string; label: string }[] };
};
type Bench = {
  incidents_total: number; attacks_correlated: number; techniques_mapped: number;
  mapping_rate: number | null; contained: number; postmortems_written: number;
};

export default function ShieldPage() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [bench, setBench] = useState<Bench | null>(null);
  const [live, setLive] = useState(false);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  async function load() {
    try {
      const i = await api<{ incidents: Incident[] }>("/api/shield/incidents");
      setIncidents(i.incidents);
      setBench(await api<Bench>("/api/shield/benchmark"));
    } catch (err) {
      setNote(err instanceof Error ? err.message : "SHIELD API failed");
    }
  }

  useEffect(() => {
    load();
    const refresh = setInterval(load, 10000);
    const stop = streamSSE("/api/shield/stream", (ev) => {
      if (ev.kind === "incident") {
        setLive(true);
        setTimeout(() => setLive(false), 2000);
        load();
      }
    });
    return () => { clearInterval(refresh); stop(); };
  }, []);

  async function fireAttack() {
    setBusy(true);
    setNote(null);
    try {
      const r = await api<{ scenario: string; events: number }>("/api/shield/lab/attack", {
        method: "POST", body: JSON.stringify({}),
      });
      setNote(`attack playbook "${r.scenario}" streaming ${r.events} events — detector ticks every 5s`);
      setTimeout(load, 8000);
    } catch (err) {
      setNote(err instanceof Error ? err.message : "failed");
    } finally {
      setBusy(false);
    }
  }

  const mappingRate = bench?.mapping_rate != null ? Math.round(bench.mapping_rate * 100) : null;

  return (
    <>
      <div className="pagehead">
        <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 6 }}>
          <span className={`dot ${live ? "dot--live" : "dot--olive"}`} />
          <span className="label label--accent">◈ SHIELD · AI SOC ANALYST</span>
          <span className="stamp stamp--phase">PHASE 4</span>
        </div>
        <h1 className="display">SHIELD.</h1>
        <p>
          Synthetic lab playbooks mapped to MITRE ATT&amp;CK — not Wazuh, Suricata,
          or Atomic Red Team on VMs. Neo4j only if <span className="mono">ASTRAEA_NEO4J_URL</span> is set.
        </p>
      </div>

      {/* ── Instrument panel ── */}
      <div className="instrument-grid">
        <div className="instrument glass-card">
          <p className="inst-label">incidents</p>
          <div className="inst-value">{bench?.incidents_total ?? "—"}</div>
        </div>
        <div className="instrument glass-card">
          <p className="inst-label">correlated</p>
          <div className="inst-value inst-value--accent">{bench?.attacks_correlated ?? "—"}</div>
        </div>
        <div className="instrument glass-card">
          <p className="inst-label">techniques mapped</p>
          <div className="inst-value">{bench?.techniques_mapped ?? "—"}</div>
        </div>
        <div className="instrument glass-card">
          <p className="inst-label">mapping rate</p>
          <div className="inst-value">{mappingRate != null ? `${mappingRate}%` : "—"}</div>
          {mappingRate != null && (
            <div className="progress-track" style={{ marginTop: 8 }}>
              <div className={`progress-fill ${mappingRate >= 80 ? "progress-fill--olive" : "progress-fill--amber"}`}
                   style={{ width: `${mappingRate}%` }} />
            </div>
          )}
        </div>
        <div className="instrument glass-card">
          <p className="inst-label">contained</p>
          <div className="inst-value">{bench?.contained ?? "—"}</div>
        </div>
      </div>

      {/* ── Red team control ── */}
      <div className="glass-card" style={{ padding: 18, marginBottom: 22, display: "flex", gap: 16, alignItems: "center", flexWrap: "wrap" }}>
        <span className="label label--accent">LAB · RED TEAM</span>
        <span style={{ flex: 1, fontSize: 13, color: "var(--ink-70)" }}>
          Fire a random attack playbook (brute force → valid accounts · lateral movement ·
          malicious process · data exfil · C2 beaconing).
        </span>
        <button className="btn btn--accent" disabled={busy} onClick={fireAttack}>
          {busy ? "launching…" : "Fire random attack ⚡"}
        </button>
      </div>
      {note && <div className="glass-card" style={{ padding: "10px 16px", marginBottom: 16 }}><span className="label">{note}</span></div>}

      {/* ── Detection rules ── */}
      <div className="glass-card" style={{ padding: 16, marginBottom: 22 }}>
        <p className="label label--ink" style={{ marginBottom: 8 }}>DETECTION RULES (data, not code)</p>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {[
            { id: "T1110", desc: "brute force — 5 failures/60s" },
            { id: "T1078", desc: "success after failures" },
            { id: "T1046", desc: "8 distinct ports/60s" },
            { id: "T1041", desc: "4MB outbound to external" },
            { id: "T1071.001", desc: "fixed-interval beaconing" },
            { id: "T1059", desc: "suspicious process patterns" },
          ].map((r) => (
            <span key={r.id} className="stamp stamp--phase" style={{ transform: "none" }}>{r.id} · {r.desc}</span>
          ))}
        </div>
      </div>

      {/* ── Incident war room ── */}
      <section>
        <p className="label label--ink" style={{ marginBottom: 12 }}>INCIDENT WAR ROOM — newest first</p>
        {incidents.length === 0 && (
          <div className="empty">all clear. fire a lab attack above — incidents appear here in
            real time with their ATT&amp;CK mapping and attack graph.</div>
        )}
        <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 26 }}>
          {incidents.map((inc) => (
            <div key={inc.id} className="glass-card" style={{ padding: 0, overflow: "hidden" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center",
                            padding: "10px 16px", borderBottom: "1px solid var(--line)" }}>
                <span className="label">#{inc.id} · {inc.host} · {inc.detected_at.slice(0, 19)} · {inc.severity}</span>
                <span style={{ display: "flex", gap: 8 }}>
                  <span className="stamp">{inc.status}</span>
                  {inc.run_id && <Link href={`/console/runs/${inc.run_id}`} className="stamp stamp--used">SHIELD RUN →</Link>}
                </span>
              </div>
              <div style={{ padding: "12px 16px" }}>
                {inc.narrative && <p style={{ margin: "0 0 10px", fontSize: 13.5, color: "var(--ink-70)" }}>{inc.narrative}</p>}
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 10 }}>
                  {inc.techniques.map((t) => (
                    <span key={t.id} className="stamp stamp--phase">{t.id} · {t.tactic}</span>
                  ))}
                </div>
                {inc.attack_graph?.edges && inc.attack_graph.edges.length > 0 && (
                  <div className="glass" style={{ padding: 12, fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--ink-70)" }}>
                    <p className="label label--accent" style={{ margin: "0 0 6px" }}>ATTACK GRAPH</p>
                    {inc.attack_graph.edges.map((e, i) => (
                      <div key={i}>
                        {e.src} <span style={{ color: "var(--accent)" }}>──{e.label}──▶</span> {e.dst}
                      </div>
                    ))}
                  </div>
                )}
                {inc.containment && (
                  <p className="label" style={{ marginTop: 8 }}>
                    containment: {JSON.stringify(inc.containment.applied)}
                  </p>
                )}
              </div>
            </div>
          ))}
        </div>
      </section>

      <div className="footer-strip">
        <span className="label">postmortems flow to medic · operator · forge via loom — provenance stamped</span>
      </div>
    </>
  );
}
