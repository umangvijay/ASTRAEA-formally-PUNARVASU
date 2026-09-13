export default function Doc() {
  return (
    <>
      <span className="label label--accent">MEDIC · AI SRE</span>
      <h1 className="display">The on-call engineer that never sleeps.</h1>
      <p style={{ color: "var(--ink-70)", fontSize: 15 }}>
        MEDIC watches this control plane&apos;s live request latency, error rate and CPU
        (plus any series you ingest via <span className="mono">POST /api/pulse/ingest</span> or OTLP).
        It detects drift, ranks why, reproduces against the live series — then prepares
        the fix and asks you before applying anything. Demo sidecars are optional on a laptop.
      </p>

      <h2 className="display" style={{ fontSize: 21, marginTop: 30 }}>What you use it for</h2>
      <ul style={{ color: "var(--ink-70)", fontSize: 14.5, lineHeight: 1.8 }}>
        <li><b>Catch outages before users notice</b> — an Isolation Forest model learns each service&apos;s normal behaviour and flags deviations (error bursts, latency spikes, memory leaks).</li>
        <li><b>Know <i>why</i>, not just <i>what</i></b> — MEDIC ranks root-cause hypotheses using telemetry drift, service configs, its past fixes (from Memory) and an AI investigation.</li>
        <li><b>Safe fixes</b> — the fix is generated as a real diff and only applied after you approve. With a GitHub token configured, it opens a pull request instead.</li>
      </ul>

      <h2 className="display" style={{ fontSize: 21, marginTop: 30 }}>How it works</h2>
      <div className="docs-steps">
        <div className="docs-step"><span className="n">1</span><div><b>Learn</b> — every 10 seconds, the detector fits a fresh model on each service&apos;s recent telemetry (trained only on clean history, with 3-point voting so one noisy frame can&apos;t page you).</div></div>
        <div className="docs-step"><span className="n">2</span><div><b>Detect</b> — a significant drift (+2.5σ) that the forest also flags becomes an anomaly, linked to any recent deploy or config change.</div></div>
        <div className="docs-step"><span className="n">3</span><div><b>Investigate</b> — a durable run starts: gather evidence → rank hypotheses → verify against live series (or a demo /diagnose endpoint) → stop at your approval gate.</div></div>
        <div className="docs-step"><span className="n">4</span><div><b>Fix</b> — on your approval: generate the config diff, apply it, save a patch file, write the postmortem to Memory.</div></div>
      </div>

      <h2 className="display" style={{ fontSize: 21, marginTop: 30 }}>How to use it</h2>
      <div className="docs-steps">
        <div className="docs-step"><span className="n">1</span><div>Open <b>MEDIC</b>. Click <b>⚡ Inject random fault</b> — chaos distorts this API&apos;s live series (or a demo sidecar if one is running locally), with auto-recovery.</div></div>
        <div className="docs-step"><span className="n">2</span><div>Watch the anomaly appear in seconds (MTTD under 2 minutes), then click <b>MEDIC RUN →</b>.</div></div>
        <div className="docs-step"><span className="n">3</span><div>Read the investigation, click <b>Approve →</b> and see the fix diff applied.</div></div>
      </div>
      <p style={{ color: "var(--ink-70)", fontSize: 15 }}>The scoreboard (faults, detection %, MTTD) tracks itself — that&apos;s the benchmark, always visible.</p>
    </>
  );
}
