import { FlowDiagram, PipelineDiagram } from "@/components/ArchDiagram";

export default function Doc() {
  return (
    <>
      <span className="label label--accent">OPERATOR · LIVE WEB + COMPUTER-USE</span>
      <h1 className="display">Finds real pages. Then works the screen.</h1>
      <p style={{ color: "var(--ink-70)", fontSize: 15 }}>
        Google, ChatGPT, Claude and Cursor all look the same to a headless browser
        (login walls). OPERATOR therefore <b>searches and fetches the public web</b>
        first — DuckDuckGo or Brave — and only then clicks where a real GUI exists.
        Every result carries that URL&apos;s live HTML. Nothing is canned.
      </p>
      <PipelineDiagram
        title="RESEARCH PIPELINE"
        stages={[
          { id: "query", label: "Your goal", detail: "Typed in the console. Never a hardcoded prompt." },
          { id: "search", label: "Live index", detail: "Brave if keyed, else DuckDuckGo Instant + HTML." },
          { id: "fetch", label: "Real HTML", detail: "SSRF-guarded GET. Title + text extracted from that response." },
          { id: "sentinel", label: "Optional fold", detail: "SENTINEL → Vertex / Gemini / Claude / Groq / Ollama." },
          { id: "loom", label: "Stamped memory", detail: "Provenance: born in OPERATOR, shareable with MEDIC and SHIELD." },
        ]}
      />
      <FlowDiagram
        title="THEN, IF A REAL GUI EXISTS"
        steps={[
          { id: "ground", label: "DOM + SoM" },
          { id: "decide", label: "vision chain" },
          { id: "act", label: "isolated browser" },
          { id: "verify", label: "pixel diff" },
          { id: "remember", label: "trajectory" },
        ]}
      />

      <h2 className="display" style={{ fontSize: 21, marginTop: 30 }}>What you use it for</h2>
      <ul style={{ color: "var(--ink-70)", fontSize: 14.5, lineHeight: 1.8 }}>
        <li><b>Live research</b> — search the public web, fetch each hit, and read <em>that</em> page&apos;s text. Google / ChatGPT / Claude / Cursor queries become real excerpts, not a template.</li>
        <li><b>Repetitive web work</b> — category browsing, portal logins, form filling, data lookups on sites you don&apos;t control.</li>
        <li><b>Self-checking automation</b> — every action is verified by a pixel-diff and URL/content check; silent failures trigger a replan instead of continuing blindly.</li>
        <li><b>Learning</b> — successful action sequences are saved to Memory; a repeated task can replay the learned trajectory instead of re-planning.</li>
      </ul>

      <h2 className="display" style={{ fontSize: 21, marginTop: 30 }}>How it works</h2>
      <p style={{ color: "var(--ink-70)", fontSize: 15 }}>
        Each step: <b>ground</b> the page (real DOM boxes → every clickable element numbered,
        Set-of-Mark overlay), <b>decide</b> the next action (Gemini vision → local Ollama vision →
        an evidence-based scoring planner — always a fallback chain), <b>act</b> in an isolated
        Chromium with a throwaway profile, <b>verify</b> the change, <b>replan</b> when a step
        didn&apos;t work. The whole loop runs as a durable run, so you watch it live and replay later.
      </p>

      <h2 className="display" style={{ fontSize: 21, marginTop: 30 }}>How to use it</h2>
      <div className="docs-steps">
        <div className="docs-step"><span className="n">1</span><div>Open <b>OPERATOR</b>. Use <b>Live web research</b> for Google / GitHub / ChatGPT-style questions — each card is a different live URL.</div></div>
        <div className="docs-step"><span className="n">2</span><div>For a real GUI, enter a goal and start URL. Optionally set <b>success when URL contains</b>.</div></div>
        <div className="docs-step"><span className="n">3</span><div><b>Execute →</b> and watch the actions stream under Runs. Walled gardens skip the fake click-loop and keep the research pack.</div></div>
      </div>
      <p style={{ color: "var(--ink-70)", fontSize: 15 }}>All permissions are denied in the browser profile and no host files are touched — the site is the only surface.</p>
    </>
  );
}
