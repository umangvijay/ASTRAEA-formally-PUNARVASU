import { PublicNav } from "@/components/PublicNav";

export default function Terms() {
  return (
    <>
      <PublicNav />
      <section className="hero" style={{ padding: "60px 34px 30px" }}>
        <span className="label label--accent">TERMS</span>
        <h1 className="display" style={{ marginTop: 12 }}>Terms of Service.</h1>
      </section>
      <section className="section" style={{ paddingTop: 10 }}>
        <div className="faq-item"><h3>1. Acceptance</h3><p>By using Astraea you agree to these terms. If you don&apos;t agree, don&apos;t use the platform.</p></div>
        <div className="faq-item"><h3>2. The service</h3><p>Astraea provides autonomous AI agents that operate on your data and connected services. The agents are tools — you are responsible for reviewing and approving their actions.</p></div>
        <div className="faq-item"><h3>3. Guest access</h3><p>Guest workspaces are time-boxed (30 minutes) and provided as-is. Data created in guest mode expires with the session unless migrated.</p></div>
        <div className="faq-item"><h3>4. Security</h3><p>We apply Argon2id password hashing, JWT sessions, security headers, rate limiting and sandboxed execution — but no system is perfect. Report vulnerabilities to umangvijay025@gmail.com.</p></div>
        <div className="faq-item"><h3>5. Liability</h3><p>Astraea is provided without warranty. We are not liable for indirect damages arising from agent actions taken under your approval.</p></div>
      </section>
      <footer style={{ padding: "26px 34px", borderTop: "1px solid var(--line)" }}>
        <span className="label">© 2026 Astraea</span>
      </footer>
    </>
  );
}
