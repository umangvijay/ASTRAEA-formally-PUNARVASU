"use client";

import { FormEvent, useState } from "react";
import { PublicNav } from "@/components/PublicNav";
import { resolveApiBase } from "@/lib/api";

export default function Contact() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      const base = await resolveApiBase();
      const r = await fetch(`${base}/api/contact`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, email, message }),
      });
      if (!r.ok) throw new Error((await r.json()).detail ?? "failed");
      setSent(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "failed to send");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PublicNav />
      <section className="hero">
        <div className="observatory-plaque">
          <span className="label label--accent">CONTACT US</span>
          <h1 className="display" style={{ marginTop: 12 }}>Let&apos;s talk.</h1>
          <p className="lead">Questions, partnerships, enterprise deployments — send a message and we&apos;ll get back to you.</p>
        </div>
      </section>
      <section className="section" style={{ paddingTop: 10 }}>
        <div className="cards3">
          <div>
            <div className="panel glass" style={{ marginBottom: 16 }}>
              <h3 style={{ marginTop: 0 }}>Umang Vijay</h3>
              <p style={{ fontSize: 13.5, color: "var(--ink-70)", margin: "0 0 10px" }}>Founder & Developer</p>
              <p style={{ fontSize: 13.5, margin: 0 }}>
                <a href="https://github.com/umangvijay" target="_blank" rel="noopener noreferrer" style={{ color: "var(--accent)" }}>GitHub ↗</a>
                {" · "}
                <a href="https://www.linkedin.com/in/umangvijay/" target="_blank" rel="noopener noreferrer" style={{ color: "var(--accent)" }}>LinkedIn ↗</a>
              </p>
              <p style={{ fontSize: 13.5, margin: "8px 0 0" }}>
                <a href="mailto:umangvijay35@gmail.com" style={{ color: "var(--accent)" }}>umangvijay35@gmail.com</a>
              </p>
            </div>
            <div className="panel glass">
              <p className="label label--ink">response time</p>
              <p style={{ fontSize: 13.5, color: "var(--ink-70)", margin: "6px 0 0" }}>Usually within 24 hours. Enterprise queries are prioritised.</p>
            </div>
          </div>
          <div className="panel glass span-all">
            {sent ? (
              <div style={{ textAlign: "center", padding: 30 }}>
                <h3 className="display">Message received</h3>
                <p style={{ color: "var(--ink-70)", fontSize: 14 }}>
                  Stored in the control plane for the founder. This Cloud Run
                  service does not send email. If it is urgent, write{" "}
                  <a href="mailto:umangvijay35@gmail.com" style={{ color: "var(--accent)" }}>umangvijay35@gmail.com</a>.
                </p>
                <button className="btn btn--ghost" onClick={() => { setSent(false); setMessage(""); }}>Send another</button>
              </div>
            ) : (
              <form onSubmit={submit}>
                <h3 style={{ marginTop: 0 }}>Send a Message</h3>
                <div className="field"><span className="label">Your name</span>
                  <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Ada Lovelace" required minLength={1} /></div>
                <div className="field"><span className="label">Your email</span>
                  <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" required /></div>
                <div className="field"><span className="label">Message</span>
                  <textarea value={message} onChange={(e) => setMessage(e.target.value)}
                            placeholder="How can Astraea help you?" required minLength={5}
                            rows={5} style={{ width: "100%", background: "transparent", border: "1px solid var(--line)", padding: 12, color: "var(--ink)", fontFamily: "var(--font-mono)", fontSize: 13, resize: "vertical" }} /></div>
                {error && <div className="err">✕ {error}</div>}
                <button className="btn btn--accent" disabled={busy} style={{ width: "100%", padding: 13 }}>
                  {busy ? "sending…" : "Send message →"}
                </button>
              </form>
            )}
          </div>
        </div>
      </section>
      <footer className="site-footer">
        <span className="label">© 2026 Astraea</span>
      </footer>
    </>
  );
}
