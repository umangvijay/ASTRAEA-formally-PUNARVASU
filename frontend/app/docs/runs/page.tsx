export default function Doc() {
  return (
    <>
      <span className="label label--accent">RUNS</span>
      <h1 className="display">Jobs that never get lost.</h1>
      <p style={{ color: "var(--ink-70)", fontSize: 15 }}>A <b>run</b> is one job an agent does for you. Every step is written down as it happens — so nothing is ever lost, and you can replay exactly what happened, any time.</p>

      <h2 className="display" style={{ fontSize: 21, marginTop: 30 }}>Why it matters</h2>
      <ul style={{ color: "var(--ink-70)", fontSize: 14.5, lineHeight: 1.8 }}>
        <li><b>Crashes don&apos;t kill jobs</b> — restart the platform mid-run and it resumes exactly where it stopped.</li>
        <li><b>You are the safety gate</b> — before an agent applies a fix or contains an attack, the run pauses as <b>WAITING FOR YOU</b>. It can wait for days.</li>
        <li><b>Full replay</b> — every event with its inputs, outputs and token cost is stored. &quot;What did the agent do last Tuesday?&quot; is one click.</li>
      </ul>

      <h2 className="display" style={{ fontSize: 21, marginTop: 30 }}>How it works</h2>
      <p style={{ color: "var(--ink-70)", fontSize: 15 }}>
        Each run is a list of steps (a recipe): tools to run, AI calls to make, memory writes, and approval gates. The engine executes them one by one, appending an event per step to the database and streaming it live to your browser. Status is always reconstructable from the event log — that&apos;s what makes it durable. A self-healing watchdog also marks any run stuck mid-flight as <b>PAUSED</b> so you can resume it.
      </p>

      <h2 className="display" style={{ fontSize: 21, marginTop: 30 }}>Status chips</h2>
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
        <span className="stamp status-chip st-run">RUNNING</span>
        <span className="stamp status-chip st-wait">WAITING FOR YOU</span>
        <span className="stamp status-chip st-done">DONE</span>
        <span className="stamp status-chip st-fail">FAILED</span>
        <span className="stamp status-chip st-wait">PAUSED</span>
      </div>

      <h2 className="display" style={{ fontSize: 21, marginTop: 30 }}>How to use it</h2>
      <div className="docs-steps">
        <div className="docs-step"><span className="n">1</span><div>Open <b>Runs</b> — waiting decisions are pinned at the top with <b>Decide →</b>.</div></div>
        <div className="docs-step"><span className="n">2</span><div>Start a new job: describe what you want, pick a recipe, <b>Start the job →</b>.</div></div>
        <div className="docs-step"><span className="n">3</span><div>On a run page: watch the event log stream, approve/reject gates, resume paused runs, read final outputs.</div></div>
      </div>
    </>
  );
}
