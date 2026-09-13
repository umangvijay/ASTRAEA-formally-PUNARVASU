"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, streamSSE } from "@/lib/api";

type Anomaly = {
  id: number; service: string; score: number; run_id: string | null;
  metrics: Record<string, number>; evidence: { drifted: string; drift_sigma: number };
  detected_at: string;
};
type Benchmark = {
  faults_injected: number; detected: number; detection_rate: number | null;
  mttd_seconds_avg: number | null; mttd_target_seconds: number;
  top3_accuracy: number | null; top3_target: number;
};

export default function MedicPage() {
  const [anomalies, setAnomalies] = useState<Anomaly[]>([]);
  const [bench, setBench] = useState<Benchmark | null>(null);
  const [live, setLive] = useState(false);
  const [chaosBusy, setChaosBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  async function load() {
    try {
      const a = await api<{ anomalies: Anomaly[] }>("/api/pulse/anomalies");
      setAnomalies(a.anomalies);
      setBench(await api<Benchmark>("/api/pulse/benchmark"));
    } catch (err) {
      setNote(err instanceof Error ? err.message : "MEDIC API failed");
    }
  }

  useEffect(() => {
    load();
    const refresh = setInterval(load, 10000);
    const stop = streamSSE("/api/pulse/stream", (ev) => {
      if (ev.kind === "anomaly") {
        setLive(true);
        setTimeout(() => setLive(false), 2000);
        load();
      }
    });
    return () => { clearInterval(refresh); stop(); };
  }, []);

  async function injectFault() {
    setChaosBusy(true);
    setNote(null);
    try {
      const r = await api<{ service: string; fault: string; auto_recover_s: number }>("/api/pulse/chaos", {
        method: "POST", body: JSON.stringify({}),
      });
      setNote(`chaos: ${r.fault} rolled to ${r.service} — auto-recover in ${r.auto_recover_s}s. watch the detector.`);
      setTimeout(load, 3000);
    } catch (err) {
      setNote(err instanceof Error ? err.message : "chaos failed");
    } finally {
      setChaosBusy(false);
    }
  }

  const detectionRate = bench?.detection_rate != null ? Math.round(bench.detection_rate * 100) : null;
  const top3 = bench?.top3_accuracy != null ? Math.round(bench.top3_accuracy * 100) : null;

  return (
    <>
      <div className="pagehead">
        <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 6 }}>
          <span className={`dot ${live ? "dot--live" : "dot--olive"}`} />
          <span className="label label--accent">◈ MEDIC · AI SRE</span>
          <span className="stamp stamp--phase">PHASE 2</span>
        </div>
        <h1 className="display">MEDIC.</h1>
        <p>
          Isolation Forest on demo (or your) telemetry. Reproduce hits{" "}
          <span className="mono">/diagnose</span> on a demo service. Patch writes
          local config.json. GitHub PR only if token+repo are set. Chaos needs{" "}
          <span className="mono">python3 main.py --profile sre</span>.
        </p>
      </div>

      {/* ── Instrument panel ── */}
      <div className="instrument-grid">
        <div className="instrument glass-card">
          <p className="inst-label">faults injected</p>
          <div className="inst-value">{bench?.faults_injected ?? "—"}</div>
        </div>
        <div className="instrument glass-card">
          <p className="inst-label">detected</p>
          <div className="inst-value inst-value--accent">{bench?.detected ?? "—"}</div>
        </div>
        <div className="instrument glass-card">
          <p className="inst-label">detection rate</p>
          <div className="inst-value">{detectionRate != null ? `${detectionRate}%` : "—"}</div>
          {detectionRate != null && (
            <div className="progress-track" style={{ marginTop: 8 }}>
              <div className={`progress-fill ${detectionRate >= 80 ? "progress-fill--olive" : "progress-fill--amber"}`}
                   style={{ width: `${detectionRate}%` }} />
            </div>
          )}
        </div>
        <div className="instrument glass-card">
          <p className="inst-label">MTTD avg</p>
          <div className="inst-value">{bench?.mttd_seconds_avg != null ? `${bench.mttd_seconds_avg}s` : "—"}</div>
          <p className="inst-trend">target &lt; {bench?.mttd_target_seconds ?? 120}s</p>
        </div>
        <div className="instrument glass-card">
          <p className="inst-label">top-3 accuracy</p>
          <div className="inst-value">{top3 != null ? `${top3}%` : "—"}</div>
          <p className="inst-trend">target ≥ {bench ? Math.round(bench.top3_target * 100) : 70}%</p>
        </div>
      </div>

      {/* ── Chaos control ── */}
      <div className="glass-card" style={{ padding: 18, marginBottom: 22, display: "flex", gap: 16, alignItems: "center", flexWrap: "wrap" }}>
        <span className="label label--accent">CHAOS CONTROL</span>
        <span style={{ flex: 1, fontSize: 13, color: "var(--ink-70)" }}>
          Inject a random fault into a random demo service. Unscripted — the detector has to earn it.
        </span>
        <button className="btn btn--accent" disabled={chaosBusy} onClick={injectFault}>
          {chaosBusy ? "injecting…" : "Inject random fault ⚡"}
        </button>
      </div>
      {note && <div className="glass-card" style={{ padding: "10px 16px", marginBottom: 16 }}><span className="label">{note}</span></div>}

      {/* ── Pipeline steps ── */}
      <div className="glass-card" style={{ padding: 16, marginBottom: 22 }}>
        <p className="label label--ink" style={{ marginBottom: 8 }}>PIPELINE</p>
        <div style={{ display: "flex", gap: 0, flexWrap: "wrap" }}>
          {["detect · isolation forest", "investigate · llm + evidence", "reproduce · probe service", "approve · your decision", "fix · real diff → PR"].map((step, i) => (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span className="stamp" style={{ transform: "none", fontSize: 9 }}>{i + 1}</span>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--ink-70)", whiteSpace: "nowrap" }}>{step}</span>
              {i < 4 && <span style={{ color: "var(--ink-30)", margin: "0 8px" }}>→</span>}
            </div>
          ))}
        </div>
      </div>

      {/* ── Anomaly feed ── */}
      <section>
        <p className="label label--ink" style={{ marginBottom: 12 }}>ANOMALY FEED — newest first</p>
        {anomalies.length === 0 && (
          <div className="empty">all quiet. inject a fault above — detection lands here in seconds,
            and a medic run starts on its own.</div>
        )}
        <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 26 }}>
          {anomalies.map((a) => (
            <div key={a.id} className="glass-card" style={{ padding: 0, overflow: "hidden" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center",
                            padding: "10px 16px", borderBottom: "1px solid var(--line)" }}>
                <span className="label">#{a.id} · {a.detected_at.slice(0, 19)} · score {a.score}</span>
                {a.run_id ? (
                  <Link href={`/console/runs/${a.run_id}`} className="stamp stamp--used">MEDIC RUN →</Link>
                ) : (
                  <span className="stamp stamp--local">SPAWNING…</span>
                )}
              </div>
              <div style={{ padding: "12px 16px" }}>
                <p style={{ margin: "0 0 4px", fontWeight: 600, fontFamily: "var(--font-mono)", fontSize: 14 }}>
                  {a.service} — drift in {a.evidence.drifted} ({a.evidence.drift_sigma}σ)
                </p>
                <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
                  <span className="label">rate {a.metrics.request_rate}</span>
                  <span className="label">err {a.metrics.error_rate}%</span>
                  <span className="label">p95 {a.metrics.p95_latency}ms</span>
                  <span className="label">cpu {a.metrics.cpu}%</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

      <div className="footer-strip">
        <span className="label">telemetry store: sqlite (lite) / clickhouse (docker) · incidents shared to shield via loom</span>
      </div>
    </>
  );
}
