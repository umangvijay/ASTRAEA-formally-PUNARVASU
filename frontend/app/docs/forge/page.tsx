export default function Doc() {
  return (
    <>
      <span className="label label--accent">FORGE · SELF-IMPROVEMENT LOOP</span>
      <h1 className="display">The platform that studies its own failures.</h1>
      <p style={{ color: "var(--ink-70)", fontSize: 15 }}>
        Most agents are frozen at the quality they shipped with. FORGE mines real failures
        every night, proposes improvements, tests them on a verifiable exam — and only
        promotes a change that measurably beats the current champion.
      </p>

      <h2 className="display" style={{ fontSize: 21, marginTop: 30 }}>What you use it for</h2>
      <ul style={{ color: "var(--ink-70)", fontSize: 14.5, lineHeight: 1.8 }}>
        <li><b>Guaranteed-honest improvement</b> — the eval is code, not opinion: a candidate&apos;s SQL must execute and return the exact gold rows. No vibes.</li>
        <li><b>Failure mining</b> — real <span className="mono">step_failed</span> events across your runs are clustered; recurring failures become improvement proposals.</li>
        <li><b>An audit trail for intelligence</b> — every eval run is recorded; every promotion is a commit to the agent&apos;s own git repo (<span className="mono">data/forge/repo</span>).</li>
      </ul>

      <h2 className="display" style={{ fontSize: 21, marginTop: 30 }}>How it works</h2>
      <p style={{ color: "var(--ink-70)", fontSize: 15 }}>
        The nightly consolidator: mine failures → propose a candidate (a prompt variant or
        model) → run the held-out SQL suite through the candidate → compare score with the
        reigning champion → promote only if strictly better, then git-commit the champion.
        The same gate guards manual candidates: you propose, the exam decides.
      </p>

      <h2 className="display" style={{ fontSize: 21, marginTop: 30 }}>How to use it</h2>
      <div className="docs-steps">
        <div className="docs-step"><span className="n">1</span><div>Open <b>FORGE</b> — see the current champion, its score, and the eval-history chart.</div></div>
        <div className="docs-step"><span className="n">2</span><div>Click <b>Eval prompt variant</b> to test a new idea against the champion.</div></div>
        <div className="docs-step"><span className="n">3</span><div>Let it run nightly — the chart is the week-over-week proof the system is getting better.</div></div>
      </div>
    </>
  );
}
