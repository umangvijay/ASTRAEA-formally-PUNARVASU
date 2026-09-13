export default function Doc() {
  return (
    <>
      <span className="label label--accent">SHIELD · AI SOC ANALYST</span>
      <h1 className="display">The security analyst on watch.</h1>
      <p style={{ color: "var(--ink-70)", fontSize: 15 }}>
        SHIELD is strictly defensive: it watches this tenant&apos;s real auth, guest
        sessions and SENTINEL blocks, recognizes ATT&amp;CK patterns, explains them in
        plain language, and drafts containment — you approve before anything is blocked.
        Optional red-team playbooks still exist under Lab attack.
      </p>

      <h2 className="display" style={{ fontSize: 21, marginTop: 30 }}>What you use it for</h2>
      <ul style={{ color: "var(--ink-70)", fontSize: 14.5, lineHeight: 1.8 }}>
        <li><b>Detect real attack patterns</b> — brute-force logins, password spraying then success, port scans, large data exfiltration, beaconing to command-and-control, malicious scripts — all mapped to MITRE ATT&amp;CK techniques.</li>
        <li><b>Understand attacks fast</b> — incidents include a written narrative, the attack graph (who reached which host), and the exact rules that fired.</li>
        <li><b>Contain with confidence</b> — the recommended containment (block IP, lock user) waits at your approval gate; once approved, the lab honours it — blocked IPs really are dropped.</li>
        <li><b>Prove your false-positive rate</b> — a 24-hour benign-traffic drill (lab flag) replays honest day-to-day activity through the same detector. Alice/bob heartbeats stay off on Cloud Run unless <span className="mono">ASTRAEA_SHIELD_LAB=1</span>.</li>
      </ul>

      <h2 className="display" style={{ fontSize: 21, marginTop: 30 }}>How it works</h2>
      <p style={{ color: "var(--ink-70)", fontSize: 15 }}>
        Detection rules are database rows (evaluator + threshold + ATT&amp;CK technique), so
        thresholds aren&apos;t magic numbers in code. Every 5 seconds the detector replays the
        recent event window through every enabled rule; hits are deduplicated per host,
        an incident is written, and a durable SHIELD run starts: correlate → build graph →
        <b> your approval</b> → contain → postmortem to Memory.
      </p>

      <h2 className="display" style={{ fontSize: 21, marginTop: 30 }}>How to use it</h2>
      <div className="docs-steps">
        <div className="docs-step"><span className="n">1</span><div>Sign in (or continue as guest) — those events land in the store. Optional: click <b>⚡ Fire random attack</b> to run an ATT&amp;CK playbook.</div></div>
        <div className="docs-step"><span className="n">2</span><div>Incidents appear within seconds with severity, ATT&amp;CK mapping and graph. Click <b>SHIELD RUN →</b>.</div></div>
        <div className="docs-step"><span className="n">3</span><div>Review the containment recommendation, <b>Approve →</b>, and the postmortem lands in Memory stamped FROM SHIELD.</div></div>
        <div className="docs-step"><span className="n">4</span><div>Check honesty: <span className="mono">POST /api/shield/lab/benign-drill</span> runs 24h of benign traffic — false-positive rate should be ~0%.</div></div>
      </div>
    </>
  );
}
