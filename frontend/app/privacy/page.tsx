import { PublicNav } from "@/components/PublicNav";

export default function Privacy() {
  return (
    <>
      <PublicNav />
      <section className="hero">
        <div className="observatory-plaque">
          <span className="label label--accent">PRIVACY</span>
          <h1 className="display" style={{ marginTop: 12 }}>Your data, your rules.</h1>
          <p className="lead">Astraea is self-hostable and privacy-first. This page explains what we collect and why.</p>
        </div>
      </section>
      <section className="section" style={{ paddingTop: 10 }}>
        <div className="faq-item"><h3>What we collect</h3><p>Your email, an Argon2id-hashed password, and the artifacts you create in your workspace (runs, bookings, blog posts, messages). We do not sell or share your data.</p></div>
        <div className="faq-item"><h3>Where it lives</h3><p>Locally in your own Postgres/sqlite database when self-hosted. Cloud deployments use encrypted storage. The trained model and benchmark files also live on your machine.</p></div>
        <div className="faq-item"><h3>Guest mode</h3><p>Guest workspaces auto-expire after 30 minutes and carry the same protections — nothing is shared with other tenants.</p></div>
        <div className="faq-item"><h3>Retention</h3><p>You control retention per tenant via the console. Delete your workspace and all associated data is removed.</p></div>
        <div className="faq-item"><h3>Compliance</h3><p>Designed with DPDP Act 2023 (India) principles: consent, purpose limitation, and the right to erasure.</p></div>
      </section>
      <footer className="site-footer">
        <span className="label">© 2026 Astraea</span>
      </footer>
    </>
  );
}
