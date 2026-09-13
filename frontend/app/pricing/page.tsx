import Link from "next/link";
import { PublicNav } from "@/components/PublicNav";

export default function Pricing() {
  return (
    <>
      <PublicNav />
      <section className="hero">
        <div className="observatory-plaque">
          <span className="label label--accent">PRICING</span>
          <h1 className="display" style={{ marginTop: 12 }}>Start free. Scale when it works.</h1>
          <p className="lead">Every plan includes all six agents, the shared memory and the security gateway. You pay for capacity, not features.</p>
        </div>
      </section>
      <section className="section" style={{ paddingTop: 10 }}>
        <div className="cards3">
          <div className="panel glass pricing-card">
            <span className="label">SOLO — FREE</span>
            <div className="price">₹0<small>/month</small></div>
            <ul>
              <li>All six agents, solo mode</li>
              <li>Local offline models (MLX)</li>
              <li>1 workspace · community support</li>
              <li>Guest mode for collaborators</li>
            </ul>
            <Link href="/login" className="btn" style={{ width: "100%", textAlign: "center" }}>Start free →</Link>
          </div>
          <div className="panel glass pricing-card" style={{ borderColor: "var(--accent)" }}>
            <span className="stamp">MOST POPULAR</span>
            <span className="label" style={{ marginTop: 8 }}>PRO</span>
            <div className="price">₹1,999<small>/month</small></div>
            <ul>
              <li>Fusion workspace — all agents together</li>
              <li>Cloud-tier brains (Gemini/Groq) included</li>
              <li>3 workspaces · live dashboards · SLO alerts</li>
              <li>Voice employee (VAANI) telephony add-on</li>
            </ul>
            <Link href="/login" className="btn btn--accent" style={{ width: "100%", textAlign: "center" }}>Start 14-day trial →</Link>
          </div>
          <div className="panel glass pricing-card">
            <span className="label">ENTERPRISE</span>
            <div className="price">Let&apos;s talk<small>/year</small></div>
            <ul>
              <li>Self-hosted or VPC deployment</li>
              <li>SSO · audit exports · SLA 99.9%</li>
              <li>Custom vertical packs (BFSI, clinics)</li>
              <li>Dedicated onboarding engineer</li>
            </ul>
            <Link href="/contact" className="btn" style={{ width: "100%", textAlign: "center" }}>Contact us →</Link>
          </div>
        </div>
      </section>
      <footer className="site-footer">
        <span className="label">© 2026 Astraea · prices in INR, exclusive of GST</span>
      </footer>
    </>
  );
}
