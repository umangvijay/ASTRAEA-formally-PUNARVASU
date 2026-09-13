export default function Doc() {
  return (
    <>
      <span className="label label--accent">SENTINEL · SECURITY GATEWAY</span>
      <h1 className="display">The bodyguard for every AI call.</h1>
      <p style={{ color: "var(--ink-70)", fontSize: 15 }}>
        Any time any agent talks to an AI model, the request and the reply pass through
        Sentinel. It blocks prompt-injection attacks and jailbreaks, and hides private
        data (Aadhaar, PAN, phone numbers, emails, card numbers) before it ever reaches
        a model or comes back to you.
      </p>

      <h2 className="display" style={{ fontSize: 21, marginTop: 30 }}>What it protects you from</h2>
      <ul style={{ color: "var(--ink-70)", fontSize: 14.5, lineHeight: 1.8 }}>
        <li><b>Prompt injection</b> — &quot;ignore all previous instructions&quot;-style attacks are blocked before the model sees them.</li>
        <li><b>Jailbreaks</b> — &quot;developer mode&quot;, &quot;reveal your system prompt&quot; patterns are blocked.</li>
        <li><b>PII leaks</b> — Indian IDs, phones, emails and cards are redacted on the way in <i>and</i> mid-stream on the way out (a card number split across two streamed chunks still gets caught).</li>
        <li><b>Runaway costs</b> — every call is metered per workspace against a monthly token quota (2M default).</li>
      </ul>

      <h2 className="display" style={{ fontSize: 21, marginTop: 30 }}>How it works</h2>
      <p style={{ color: "var(--ink-70)", fontSize: 15 }}>
        Detection rules are <b>data in your database, not code</b> — 8 global rules ship by
        default and you can add your own regex rules, enable/disable each one, or override
        a global rule just for your workspace. Sentinel sits between every agent and the
        model chain, scanning input before the call and scanning the reply token-by-token
        as it streams, with a carry-window so patterns split across chunks are still caught.
      </p>

      <h2 className="display" style={{ fontSize: 21, marginTop: 30 }}>How to use it</h2>
      <div className="docs-steps">
        <div className="docs-step"><span className="n">1</span><div>Open <b>Sentinel</b> — see live traffic, blocked count, scan latency and your token quota.</div></div>
        <div className="docs-step"><span className="n">2</span><div>Toggle any rule <b>ON/OFF</b> — your override applies only to your workspace.</div></div>
        <div className="docs-step"><span className="n">3</span><div>Add a custom rule: a name + regex, choose block / redact / flag. It takes effect immediately.</div></div>
        <div className="docs-step"><span className="n">4</span><div>Test it: start a run whose goal contains <span className="mono">ignore all previous instructions</span> — the run fails with a guardrail event right here.</div></div>
      </div>
    </>
  );
}
