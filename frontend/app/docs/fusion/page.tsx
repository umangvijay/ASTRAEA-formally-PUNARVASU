export default function Doc() {
  return (
    <>
      <span className="label label--accent">FUSION</span>
      <h1 className="display">Mission control.</h1>
      <p style={{ color: "var(--ink-70)", fontSize: 15 }}>The one screen where you start work and watch every agent — all agents see each other&apos;s results here, with one shared timeline.</p>

      <h2 className="display" style={{ fontSize: 21, marginTop: 30 }}>What you use it for</h2>
      <ul style={{ color: "var(--ink-70)", fontSize: 14.5, lineHeight: 1.8 }}>
        <li><b>Start any job</b> — the form at the top takes a plain-English goal plus a recipe.</li>
        <li><b>Test agents instantly</b> — one-click buttons inject a service fault (MEDIC) or fire a simulated attack (SHIELD).</li>
        <li><b>See everything at once</b> — one live timeline of every agent&apos;s milestones, anomalies, incidents and memories.</li>
        <li><b>Never miss a decision</b> — anything waiting for you is pinned at the top with a <b>⚑ Review</b> button.</li>
      </ul>

      <h2 className="display" style={{ fontSize: 21, marginTop: 30 }}>How it works</h2>
      <p style={{ color: "var(--ink-70)", fontSize: 15 }}>
        Fusion reads every event your workspace produces — run milestones (started, finished, failed, waiting-for-you), MEDIC anomalies, SHIELD incidents and new memories — merges them by time, and refreshes every 10 seconds. Step-by-step chatter stays inside each run&apos;s page, so the timeline shows only what matters.
      </p>

      <h2 className="display" style={{ fontSize: 21, marginTop: 30 }}>How to use it</h2>
      <div className="docs-steps">
        <div className="docs-step"><span className="n">1</span><div>Open <b>Fusion</b> from the top bar.</div></div>
        <div className="docs-step"><span className="n">2</span><div>Type a goal, pick a recipe, click <b>Start →</b>. You&apos;re taken to the live run.</div></div>
        <div className="docs-step"><span className="n">3</span><div>Back in Fusion, watch milestones appear. Orange <b>⚑</b> entries need your decision — click <b>Review →</b> to approve or reject.</div></div>
      </div>
      <p style={{ color: "var(--ink-70)", fontSize: 15 }}><b>Tip:</b> the timeline shows relative time (just now / 5 min ago) — hover for the exact timestamp.</p>
    </>
  );
}
