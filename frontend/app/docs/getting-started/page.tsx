export default function Doc() {
  return (
    <>
      <span className="label label--accent">GETTING STARTED</span>
      <h1 className="display">Up and running in 5 minutes.</h1>

      <h2 className="display" style={{ fontSize: 21, marginTop: 30 }}>1 · Install</h2>
      <p style={{ color: "var(--ink-70)", fontSize: 15 }}>You need Python 3.11+ and Node.js. Then one command does everything — virtual environment, dependencies, database, servers:</p>
      <div className="code-block">{`python3 main.py`}</div>
      <p style={{ color: "var(--ink-70)", fontSize: 15 }}>Wait for <b>api:UP · console:UP</b>, then open <b>http://localhost:3000</b>.</p>

      <h2 className="display" style={{ fontSize: 21, marginTop: 30 }}>2 · Create your account</h2>
      <p style={{ color: "var(--ink-70)", fontSize: 15 }}>
        Click <b>Sign in → Create account</b>. This creates your private workspace —
        your data is yours, isolated from everyone else&apos;s. Or click
        <b> &quot;continue as guest&quot;</b> for a 30-minute look around.
      </p>

      <h2 className="display" style={{ fontSize: 21, marginTop: 30 }}>3 · Run your first job</h2>
      <p style={{ color: "var(--ink-70)", fontSize: 15 }}>Open <b>Fusion</b> and type what you want in plain words:</p>
      <div className="code-block">{`Goal:    take a snapshot of this machine and remember it
Recipe:  system-snapshot — no AI needed`}</div>
      <p style={{ color: "var(--ink-70)", fontSize: 15 }}>
        Click <b>Start →</b>. You land on the run page and watch each step complete live.
        The result is saved to <b>Memory</b> automatically.
      </p>

      <h2 className="display" style={{ fontSize: 21, marginTop: 30 }}>4 · Try an agent</h2>
      <div className="docs-steps">
        <div className="docs-step"><span className="n">A</span><div><b>MEDIC</b> — click <b>⚡ Break a service</b> in Fusion (or in MEDIC&apos;s page). A fault is injected into a demo service; MEDIC detects it in seconds, investigates, and asks you to approve the fix.</div></div>
        <div className="docs-step"><span className="n">B</span><div><b>SHIELD</b> — click <b>⚡ Simulate an attack</b>. A realistic attack playbook fires; SHIELD correlates it into an incident with MITRE ATT&CK mapping and asks you to approve containment.</div></div>
        <div className="docs-step"><span className="n">C</span><div><b>VAANI</b> — open the VAANI page, click <b>Call</b>, allow the microphone, and say: <i>&quot;Hi, I want to book a haircut for tomorrow at 3pm, my name is Ravi.&quot;</i> Watch the booking land in Memory.</div></div>
      </div>

      <h2 className="display" style={{ fontSize: 21, marginTop: 30 }}>5 · Point the brain at Vertex</h2>
      <p style={{ color: "var(--ink-70)", fontSize: 15 }}>
        Without a general model, Chat and research synthesis return a clear 503.
        The SQL champion is never used as the default brain.
      </p>
      <div className="code-block">{`gcloud auth application-default login
gcloud config set project YOUR_PROJECT
# .env
ASTRAEA_VERTEX_PROJECT=YOUR_PROJECT
ASTRAEA_VERTEX_LOCATION=us-central1`}</div>
      <p style={{ color: "var(--ink-70)", fontSize: 15 }}>
        Restart <span className="mono">python3 main.py</span>. Then open{" "}
        <a href="/console/chat">Chat</a> or Fusion recipe <b>research-and-remember</b>.
        Full Cloud Run path: <a href="/docs/deploy">Deploy</a>.
      </p>
    </>
  );
}
