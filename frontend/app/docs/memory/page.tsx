export default function Doc() {
  return (
    <>
      <span className="label label--accent">MEMORY · LOOM</span>
      <h1 className="display">What your agents remember.</h1>
      <p style={{ color: "var(--ink-70)", fontSize: 15 }}>
        Memory is the shared notebook for all your agents. Every incident MEDIC investigated,
        every attack SHIELD contained, every booking VAANI took, every note you wrote — kept
        forever, stamped with where it came from. No agent ever asks you twice.
      </p>

      <h2 className="display" style={{ fontSize: 21, marginTop: 30 }}>What that means in practice</h2>
      <ul style={{ color: "var(--ink-70)", fontSize: 14.5, lineHeight: 1.8 }}>
        <li><b>Start with one agent, switch any time.</b> Use only SHIELD for a month; the day you switch on MEDIC, it already knows about the incident on db-1.</li>
        <li><b>Search in plain English.</b> The search bar is semantic — type <i>&quot;haircut appointment&quot;</i> and it finds VAANI&apos;s booking even if those exact words never appeared together.</li>
        <li><b>Provenance on everything.</b> Each memory shows stamps like <span className="stamp">FROM MEDIC</span> and who used it.</li>
        <li><b>You control sharing.</b> Settings → Sharing lets any module read nothing — the data stays yours.</li>
      </ul>

      <h2 className="display" style={{ fontSize: 21, marginTop: 30 }}>How it works</h2>
      <p style={{ color: "var(--ink-70)", fontSize: 15 }}>
        Every memory is stored twice: as a row in your workspace (title, summary, payload, origin) and as a <b>vector embedding</b> in a ChromaDB vector database (MiniLM model). The embedding is a numeric &quot;meaning fingerprint&quot; — similar meanings land close together, which is what makes plain-English search work. Agents also use it as RAG: before MEDIC investigates or VAANI answers, they retrieve the most relevant memories automatically.
      </p>

      <h2 className="display" style={{ fontSize: 21, marginTop: 30 }}>How to use it</h2>
      <div className="docs-steps">
        <div className="docs-step"><span className="n">1</span><div><b>Memory</b> page → type a question in the search bar → ranked results with match %.</div></div>
        <div className="docs-step"><span className="n">2</span><div>Filter by origin with the chips (ALL / MEDIC / SHIELD / …).</div></div>
        <div className="docs-step"><span className="n">3</span><div>Add your own note with the form at the bottom — every agent can read it immediately.</div></div>
      </div>
    </>
  );
}
