import Link from "next/link";
import { PublicNav } from "@/components/PublicNav";
import { LightboxGrid } from "@/components/Lightbox";
import { FlowDiagram, StackDiagram } from "@/components/ArchDiagram";
import { PLATES } from "@/lib/plates";

const CORE_GLASS = [
  { href: "/docs/sentinel", title: "SENTINEL", desc: "Every model call is scanned." },
  { href: "/docs/runs", title: "Runs", desc: "Jobs that survive crashes." },
  { href: "/docs/memory", title: "Memory", desc: "Provenance-stamped notebook." },
  { href: "/docs/security", title: "Vault", desc: "Argon2id · AES-256-GCM." },
];

const DIFFERENTIATORS = [
  {
    title: "One shared memory",
    desc: "Every agent writes what it learns into LOOM with provenance stamps. Switch products tomorrow — everything is already known.",
  },
  {
    title: "Security built-in",
    desc: "Argon2id passwords, AES-256-GCM vault, SENTINEL on every model call — Vertex, Gemini, Claude, Groq or local Ollama.",
  },
  {
    title: "Durable by design",
    desc: "Runs survive crashes, pause for your approval across days and replay from any event. Astraea means return of the light.",
  },
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
          <span className="label label--accent">ASTRAEA · the star-maiden who came back</span>
          <h1 className="display serif" style={{ marginTop: 16 }}>
            Astraea.
          </h1>
          <p className="lead">
            Six agents that do the work of humans — watched, approved and remembered.
            One shared brain. Offline on your machine. The same build on Vertex AI
            and any cloud.
          </p>
          <div className="hero-actions">
            <Link href="/login" className="btn btn--accent">Reserve a workspace →</Link>
            <Link href="#constellation" className="btn btn--ghost">See the sky map</Link>
          </div>
          <p className="hero-hint label">Scroll</p>
        </div>
      </section>

      <section className="section section--sky" id="constellation">
        <div className="sky-intro">
          <span className="label label--accent">CONSTELLATION · CLICK A PLATE TO EXPAND</span>
          <h2 className="display serif section-title">The return of light.</h2>
        </div>
        <LightboxGrid plates={PLATES} />
      </section>

      <section className="section section--sky">
        <div className="cards3">
          {CORE_GLASS.map((c) => (
            <Link key={c.href} href={c.href} className="glass-card why-card">
              <p className="label label--accent">{c.title}</p>
              <p>{c.desc}</p>
            </Link>
          ))}
        </div>
      </section>

      <section className="section">
        <span className="label label--ink">WHY IT&apos;S DIFFERENT</span>
        <h2 className="display section-title">Not a chatbot. A control plane.</h2>
        <div className="cards3" style={{ marginTop: 22 }}>
          {DIFFERENTIATORS.map((d) => (
            <div key={d.title} className="glass-card why-card">
              <h3>{d.title}</h3>
              <p>{d.desc}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="section">
        <span className="label label--ink">ARCHITECTURE · LIVE PIPELINE</span>
        <h2 className="display section-title">How work actually moves.</h2>
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

      <section className="section section--cta section--sky">
        <div className="observatory-plaque glass-card" style={{ maxWidth: 640 }}>
          <h2 className="display serif section-title">Ready to meet your first agent?</h2>
          <p className="section-lead">Free tier. No card. Your data stays yours. Runs offline without a key.</p>
          <Link href="/login" className="btn btn--accent">Create your workspace →</Link>
        </div>
      </section>

      <footer className="site-footer glass">
        <div className="site-footer-row">
          <div>
            <span className="wordmark" style={{ fontSize: 13 }}>ASTRAEA<em>.</em></span>
            <p>Control plane for autonomous agents. Same tree offline and on Vertex.</p>
          </div>
          <div className="site-footer-cols">
            <div>
              <p className="label">Product</p>
              <Link href="/pricing">Pricing</Link>
              <Link href="/docs">Docs</Link>
              <Link href="/docs/architecture">Architecture</Link>
              <Link href="/blog">Blog</Link>
            </div>
            <div>
              <p className="label">Company</p>
              <Link href="/about">About</Link>
              <Link href="/contact">Contact</Link>
              <Link href="/docs/security">Security</Link>
            </div>
          </div>
        </div>
        <div className="site-footer-base">
          <span className="label">© 2026 Astraea · return of the light</span>
        </div>
      </footer>
    </>
  );
}
