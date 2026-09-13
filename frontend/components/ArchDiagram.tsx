"use client";

/** Offline SVG diagrams — no CDN, works in light/dark. */
export function FlowDiagram({
  title, steps,
}: { title: string; steps: { id: string; label: string }[] }) {
  return (
    <div className="arch-diagram glass-card">
      <p className="label label--accent">{title}</p>
      <div className="arch-row">
        {steps.map((s, i) => (
          <div key={s.id} className="arch-node">
            <b>{s.id}</b>
            <span>{s.label}</span>
            {i < steps.length - 1 && <i className="arch-arrow" aria-hidden>→</i>}
          </div>
        ))}
      </div>
    </div>
  );
}

export function PipelineDiagram({
  title, stages,
}: { title: string; stages: { id: string; label: string; detail: string }[] }) {
  return (
    <div className="arch-diagram glass-card">
      <p className="label label--accent">{title}</p>
      <ol className="arch-pipeline">
        {stages.map((s, i) => (
          <li key={s.id}>
            <span className="n">{String(i + 1).padStart(2, "0")}</span>
            <div>
              <b className="mono">{s.id}</b>
              <strong>{s.label}</strong>
              <p>{s.detail}</p>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}

export function StackDiagram() {
  const layers = [
    { id: "console", label: "Blueprint console · SOLO / FUSION" },
    { id: "sentinel", label: "SENTINEL · Vertex / Gemini / Claude / Groq / Ollama" },
    { id: "core", label: "astra-core · leased workers · sandboxed tools" },
    { id: "loom", label: "LOOM · provenance memory · vault AES-256-GCM" },
    { id: "pulse", label: "PULSE · OTLP → SQLite / ClickHouse" },
  ];
  return (
    <div className="arch-diagram glass-card">
      <p className="label label--accent">CONTROL PLANE STACK</p>
      <ol className="arch-stack">
        {layers.map((l) => (
          <li key={l.id}><span className="mono">{l.id}</span>{l.label}</li>
        ))}
      </ol>
    </div>
  );
}
