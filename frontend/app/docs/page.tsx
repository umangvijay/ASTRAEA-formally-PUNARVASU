import Link from "next/link";
import { LightboxGrid } from "@/components/Lightbox";
import { PLATES } from "@/lib/plates";

const START = [
  { href: "/docs/getting-started", name: "Boot", what: "One command. API + console." },
  { href: "/login", name: "Workspace", what: "Create an account or guest." },
  { href: "/console/fusion", name: "Fusion", what: "Start a real job and watch it." },
  { href: "/console/chat", name: "Chat", what: "Talk through SENTINEL." },
  { href: "/docs/deploy", name: "Vertex", what: "GCloud brain — not the SQL champ." },
  { href: "/console/settings", name: "Vault", what: "Argon2id · AES-256-GCM secrets." },
];

const CORE = [
  { href: "/docs/sentinel", name: "SENTINEL", what: "Every model call is scanned." },
  { href: "/docs/runs", name: "Runs", what: "Jobs survive crashes." },
  { href: "/docs/memory", name: "Memory", what: "Provenance-stamped notebook." },
  { href: "/docs/architecture", name: "Sky map", what: "How the plane is built." },
];

export default function Docs() {
  return (
    <>
      <span className="label label--accent">OBSERVATORY · START HERE</span>
      <h1 className="display serif">Command dashboard.</h1>
      <p className="section-lead" style={{ marginTop: 8 }}>
        Same view as the console, explained. Plates below are the six workbenches.
        Core services sit under them. Nothing here is a canned demo page.
      </p>

      <div className="instrument-grid" style={{ marginTop: 22 }}>
        <div className="instrument glass-card">
          <p className="inst-label">workbenches</p>
          <div className="inst-value">6</div>
          <p className="inst-trend">MEDIC · OPERATOR · SHIELD · VAANI · FORGE · MODEL-FORGE</p>
        </div>
        <div className="instrument glass-card">
          <p className="inst-label">always on</p>
          <div className="inst-value">4</div>
          <p className="inst-trend">SENTINEL · Runs · Memory · Vault</p>
        </div>
        <div className="instrument glass-card">
          <p className="inst-label">brain</p>
          <div className="inst-value" style={{ fontSize: 16, paddingTop: 6 }}>Vertex</div>
          <p className="inst-trend">or Gemini / Groq / Ollama — never the SQL champ</p>
        </div>
      </div>

      <p className="label label--ink" style={{ margin: "28px 0 10px" }}>THE CONSTELLATION — six workbenches</p>
      <LightboxGrid plates={PLATES} />

      <p className="label label--ink" style={{ margin: "34px 0 10px" }}>START — click a tile</p>
      <div className="docs-dash">
        {START.map((s) => (
          <Link key={s.href} href={s.href}>
            <b>{s.name}</b>
            <span>{s.what}</span>
          </Link>
        ))}
      </div>

      <p className="label label--ink" style={{ margin: "34px 0 10px" }}>CORE — always running underneath</p>
      <div className="docs-dash">
        {CORE.map((s) => (
          <Link key={s.href} href={s.href}>
            <b>{s.name}</b>
            <span>{s.what}</span>
          </Link>
        ))}
      </div>

      <div className="panel" style={{ marginTop: 28 }}>
        <p className="label label--accent">GCLOUD · VERTEX</p>
        <p style={{ margin: "8px 0 0", fontSize: 14, color: "var(--ink-70)" }}>
          Chat and research synthesis need a general model. Set{" "}
          <span className="mono">ASTRAEA_VERTEX_PROJECT</span> and{" "}
          <span className="mono">gcloud auth application-default login</span>.
          Without it you get a clear 503 — not gibberish from the SQL champion.
        </p>
        <p style={{ margin: "10px 0 0" }}>
          <Link href="/docs/deploy" className="btn btn--accent" style={{ padding: "8px 14px" }}>Deploy on Vertex →</Link>
        </p>
      </div>
    </>
  );
}
