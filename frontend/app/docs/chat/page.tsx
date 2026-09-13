import Link from "next/link";

export default function Doc() {
  return (
    <>
      <span className="label label--accent">CHAT · SENTINEL</span>
      <h1 className="display">A real chat surface.</h1>
      <p style={{ color: "var(--ink-70)", fontSize: 15 }}>
        Fusion starts jobs. Chat talks to the model through SENTINEL.
        There is no hidden Studio. Open <Link href="/console/chat"><b>Console → Chat</b></Link>.
      </p>

      <h2 className="display" style={{ fontSize: 21, marginTop: 30 }}>What it does</h2>
      <ul style={{ color: "var(--ink-70)", fontSize: 14.5, lineHeight: 1.8 }}>
        <li>Every turn is <span className="mono">POST /v1/chat/completions</span>.</li>
        <li>Empty or blank content is <b>400</b> — no canned greeting.</li>
        <li>Vertex is first when <span className="mono">ASTRAEA_VERTEX_PROJECT</span> is set (ADC on GCloud).</li>
        <li>The SQL champion is never the default brain.</li>
      </ul>

      <h2 className="display" style={{ fontSize: 21, marginTop: 30 }}>If chat says 503</h2>
      <p style={{ color: "var(--ink-70)", fontSize: 15 }}>
        No general provider is ready. Set a Vertex project, a Studio/Groq key, or run Ollama.
        See <Link href="/docs/deploy">Deploy</Link>.
      </p>
    </>
  );
}
