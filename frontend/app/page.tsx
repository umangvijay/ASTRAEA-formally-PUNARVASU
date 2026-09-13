import Link from "next/link";
import { PublicNav } from "@/components/PublicNav";
import { LightboxGrid } from "@/components/Lightbox";
import { FlowDiagram, StackDiagram } from "@/components/ArchDiagram";
import { PLATES } from "@/lib/plates";

const PRODUCTS = [
  { name: "MEDIC", title: "AI SRE — the on-call engineer", blurb: "Watches live telemetry, detects anomalies, reproduces faults in a sandbox and opens the fix PR for your approval.", icon: "⚕" },
  { name: "OPERATOR", title: "Vision computer-use + live web", blurb: "Searches, fetches and reads real pages — then operates screens where no API exists, with screenshot verification.", icon: "◎" },
  { name: "SHIELD", title: "AI SOC analyst", blurb: "Correlates security events into incidents, maps MITRE ATT&CK, drafts containment for your approval.", icon: "⛊" },
  { name: "VAANI", title: "Voice AI employee", blurb: "Full-duplex voice agent that answers calls and completes the work — bookings, follow-ups, handovers.", icon: "◉" },
  { name: "FORGE", title: "Self-evolving engine", blurb: "Turns agent failures into new skills; promotes only measured improvements.", icon: "⚒" },
  { name: "MODEL-FORGE", title: "Our own model", blurb: "A domain-expert model post-trained on verifiable rewards, served behind SENTINEL.", icon: "◆" },
];

const DIFFERENTIATORS = [
  { title: "One shared memory", desc: "Every agent writes what it learns into LOOM with provenance stamps. Switch products tomorrow — everything is already known.", icon: "◈" },
  { title: "Security built-in", desc: "Argon2id passwords, AES-256-GCM vault, SENTINEL on every model call — Vertex, Gemini, Claude, Groq or local Ollama.", icon: "◇" },
  { title: "Durable by design", desc: "Runs survive crashes, pause for your approval across days and replay from any event. Astraea means return of the light.", icon: "◫" },
];

export default function Landing() {
  return (
    <>
      <PublicNav />

      <section className="hero">
        <div className="hero-copy">
          <p className="hero-meta">
            <span>a control plane</span>
            <span>solo or fusion</span>
            <span>est. return of the light</span>
          </p>
          <span className="label label--accent">
            ASTRAEA · the star-maiden who came back
          </span>
          <h1 className="display serif" style={{ marginTop: 18 }}>
            Astraea.
          </h1>
          <p className="lead">
            Six agents that do the work of humans — watched, approved and remembered.
            One shared brain. Offline on your machine. The same build on Vertex AI
            and any cloud.
          </p>
          <div style={{ display: "flex", gap: 14, marginTop: 30, flexWrap: "wrap" }}>
            <Link href="/login" className="btn btn--accent" style={{ padding: "13px 28px", fontSize: 13 }}>
              Reserve a workspace →
            </Link>
            <Link href="/docs/architecture" className="btn" style={{ padding: "13px 28px", fontSize: 13 }}>See the sky map</Link>
          </div>
          <p className="label" style={{ marginTop: 48 }}>scroll</p>
        </div>
      </section>

      <section className="section" id="constellation">
        <span className="label label--ink">CONSTELLATION · CLICK A PLATE TO EXPAND</span>
        <h2 className="display serif" style={{ fontSize: "clamp(32px, 5vw, 52px)" }}>The return of light.</h2>
        <p style={{ color: "var(--ink-70)", maxWidth: 560 }}>
          Each plate is a painted sky — earth, moon, navigator, warden, voice,
          forge. Click a plate, then open the docs. No doodle icons.
        </p>
        <LightboxGrid plates={PLATES} />
      </section>

      <section className="section" id="modules">
        <span className="label label--ink">SIX PRODUCTS · ONE CORE · ONE MEMORY</span>
        <h2 className="display">Meet the crew.</h2>
        <div className="cards3" style={{ marginTop: 22 }}>
          {PRODUCTS.map((pr) => (
            <div key={pr.name} className="glass-card" style={{ padding: 20 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
                <span style={{ fontSize: 22, opacity: 0.6 }}>{pr.icon}</span>
                <span className="label label--accent">{pr.name}</span>
              </div>
              <h3 style={{ margin: "0 0 6px", fontSize: 19 }}>{pr.title}</h3>
              <p style={{ margin: 0, fontSize: 13.5, color: "var(--ink-70)" }}>{pr.blurb}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="section" style={{ background: "var(--paper-dim)" }}>
        <span className="label label--ink">WHY IT&apos;S DIFFERENT</span>
        <h2 className="display">Not a chatbot. A control plane.</h2>
        <div className="cards3" style={{ marginTop: 22 }}>
          {DIFFERENTIATORS.map((d) => (
            <div key={d.title} className="glass-card" style={{ padding: 22 }}>
              <div style={{ fontSize: 24, marginBottom: 8, color: "var(--accent)", opacity: 0.7 }}>{d.icon}</div>
              <h3 style={{ marginTop: 0, marginBottom: 6, fontSize: 18 }}>{d.title}</h3>
              <p style={{ fontSize: 13.5, color: "var(--ink-70)", margin: 0 }}>{d.desc}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="section">
        <span className="label label--ink">ARCHITECTURE · LIVE PIPELINE</span>
        <h2 className="display">How work actually moves.</h2>
        <FlowDiagram
          title="OPERATOR WEB RESEARCH"
          steps={[
            { id: "query", label: "your goal" },
            { id: "search", label: "live index" },
            { id: "fetch", label: "real HTML" },
            { id: "sentinel", label: "scan + LLM" },
            { id: "loom", label: "stamped memory" },
          ]}
        />
        <StackDiagram />
      </section>

      <section className="section" style={{ textAlign: "center", paddingBottom: 90 }}>
        <h2 className="display serif" style={{ fontSize: "clamp(32px, 5vw, 56px)" }}>Ready to meet your first agent?</h2>
        <p style={{ color: "var(--ink-70)" }}>Free tier. No card. Your data stays yours. Runs offline without a key.</p>
        <Link href="/login" className="btn btn--accent" style={{ padding: "14px 32px", fontSize: 14 }}>
          Create your workspace →
        </Link>
      </section>

      <footer style={{ padding: "30px 34px", borderTop: "1px solid var(--line)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 30 }}>
          <div>
            <span className="wordmark" style={{ fontSize: 13 }}>ASTRAEA<em>.</em></span>
            <p style={{ fontSize: 12, color: "var(--ink-50)", marginTop: 6, maxWidth: 300 }}>
              Control plane for autonomous agents. Same tree offline and on Vertex.
            </p>
          </div>
          <div style={{ display: "flex", gap: 40 }}>
            <div>
              <p className="label" style={{ marginBottom: 8 }}>Product</p>
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <Link href="/pricing" style={{ fontSize: 13, color: "var(--ink-70)" }}>Pricing</Link>
                <Link href="/docs" style={{ fontSize: 13, color: "var(--ink-70)" }}>Docs</Link>
                <Link href="/docs/architecture" style={{ fontSize: 13, color: "var(--ink-70)" }}>Architecture</Link>
                <Link href="/blog" style={{ fontSize: 13, color: "var(--ink-70)" }}>Blog</Link>
              </div>
            </div>
            <div>
              <p className="label" style={{ marginBottom: 8 }}>Company</p>
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <Link href="/about" style={{ fontSize: 13, color: "var(--ink-70)" }}>About</Link>
                <Link href="/contact" style={{ fontSize: 13, color: "var(--ink-70)" }}>Contact</Link>
                <Link href="/docs/security" style={{ fontSize: 13, color: "var(--ink-70)" }}>Security</Link>
              </div>
            </div>
          </div>
        </div>
        <div style={{ borderTop: "1px solid var(--line)", marginTop: 24, paddingTop: 14 }}>
          <span className="label">© 2026 Astraea · return of the light</span>
        </div>
      </footer>
    </>
  );
}
