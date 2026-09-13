import { PublicNav } from "@/components/PublicNav";

export default function About() {
  return (
    <>
      <PublicNav />
      <section className="hero">
        <div className="observatory-plaque">
          <span className="label label--accent">ABOUT</span>
          <h1 className="display" style={{ marginTop: 12 }}>Built on a Sanskrit star, engineered for the long run.</h1>
          <p className="lead">Astraea (the star of return) is the Vedic nakshatra of renewal — “return of the light”. Our runtime earns the name: agent runs that die come back exactly where they stopped.</p>
        </div>
      </section>
      <section className="section">
        <div className="cards3">
          <div className="panel glass"><h3 style={{ marginTop: 0 }}>The idea</h3><p style={{ fontSize: 14, color: "var(--ink-70)", margin: 0 }}>AI agents are frozen at the quality their author shipped. We built a control plane where six agents share one durable runtime, one security gateway and one memory — so they get better every day they run.</p></div>
          <div className="panel glass"><h3 style={{ marginTop: 0 }}>The discipline</h3><p style={{ fontSize: 14, color: "var(--ink-70)", margin: 0 }}>Nothing hardcoded. Every threshold, prompt and rule lives in the database, editable in the console. Every module has a live scoreboard. Promotion only on measured improvement.</p></div>
          <div className="panel glass"><h3 style={{ marginTop: 0 }}>The promise</h3><p style={{ fontSize: 14, color: "var(--ink-70)", margin: 0 }}>Start with one product today, adopt five more next quarter — the platform already knows you. Provenance on everything; your data stays yours.</p></div>
        </div>
      </section>
      <footer className="site-footer">
        <span className="label">© 2026 Astraea</span>
      </footer>
    </>
  );
}
