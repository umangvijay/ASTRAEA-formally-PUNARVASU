import Link from "next/link";
import { FlowDiagram, PipelineDiagram, StackDiagram } from "@/components/ArchDiagram";

export default function Doc() {
  return (
    <>
      <span className="label label--accent">ARCHITECTURE · SKY MAP</span>
      <h1 className="display serif">How Astraea is built.</h1>
      <p style={{ color: "var(--ink-70)", fontSize: 15 }}>
        Same plane offline on your machine and on GCloud with Vertex (ADC).
        Diagrams below are drawn in the console — no CDN.
        Markdown twins live in <span className="mono">docs/ARCHITECTURE.md</span>.
      </p>

      <StackDiagram />

      <FlowDiagram
        title="REQUEST PATH"
        steps={[
          { id: "console", label: "Blueprint UI" },
          { id: "api", label: "FastAPI" },
          { id: "sentinel", label: "scan + route" },
          { id: "core", label: "leased run" },
          { id: "loom", label: "stamped write" },
        ]}
      />

      <PipelineDiagram
        title="OPERATOR WEB PIPELINE"
        stages={[
          { id: "goal", label: "Live input", detail: "Your words. No canned goal, no canned answer." },
          { id: "search", label: "Index", detail: "Brave or DuckDuckGo — a real query against a live index." },
          { id: "fetch", label: "Page", detail: "HTTP GET, SSRF-blocked private ranges, extracted text." },
          { id: "brain", label: "Model", detail: "Vertex on GCloud, else Gemini / Claude / Groq / Ollama." },
          { id: "memory", label: "LOOM", detail: "Provenance stamp: born in OPERATOR." },
        ]}
      />

      <h2 className="display" style={{ fontSize: 21, marginTop: 34 }}>Modules</h2>
      <p style={{ color: "var(--ink-70)", fontSize: 15 }}>
        Six products share <b>SENTINEL</b>, <b>LOOM</b> and <b>PULSE</b>. Start
        one (SOLO) or all (FUSION). Switching never re-onboards you.
      </p>
      <div className="docs-steps">
        <div className="docs-step"><span className="n">1</span><div><Link href="/docs/medic"><b>MEDIC</b></Link> — AI SRE on PULSE telemetry.</div></div>
        <div className="docs-step"><span className="n">2</span><div><Link href="/docs/operator"><b>OPERATOR</b></Link> — live web + vision computer-use.</div></div>
        <div className="docs-step"><span className="n">3</span><div><Link href="/docs/shield"><b>SHIELD</b></Link> — AI SOC, MITRE, blast radius.</div></div>
        <div className="docs-step"><span className="n">4</span><div><Link href="/docs/vaani"><b>VAANI</b></Link> — voice employee, DPDP-masked.</div></div>
        <div className="docs-step"><span className="n">5</span><div><Link href="/docs/forge"><b>FORGE</b></Link> + <Link href="/docs/model-forge"><b>MODEL-FORGE</b></Link> — skills and our SQL model.</div></div>
      </div>
    </>
  );
}
