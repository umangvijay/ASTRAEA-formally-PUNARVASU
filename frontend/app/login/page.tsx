"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api, setToken } from "@/lib/api";
import { ThemeToggle } from "@/components/ThemeToggle";

type Mode = "login" | "register";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function guest(e: React.MouseEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const body = await api<{ access_token: string; user: { tenant: { name: string } } }>(
        "/api/auth/guest", { method: "POST" });
      setToken(body.access_token);
      router.replace("/console");
    } catch (err) {
      setError(err instanceof Error ? err.message : "failed");
    } finally {
      setBusy(false);
    }
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const path = mode === "login" ? "/api/auth/login" : "/api/auth/register";
      const payload =
        mode === "login" ? { email, password } : { email, password, full_name: fullName };
      const body = await api<{ access_token: string }>(path, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setToken(body.access_token);
      router.replace("/console");
    } catch (err) {
      setError(err instanceof Error ? err.message : "something went wrong");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
    <div style={{ position: "fixed", top: 14, right: 16, zIndex: 60 }}><ThemeToggle /></div>
    <div className="login-wrap">
      <section className="login-left sheet">
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <Link href="/" className="wordmark" style={{ fontSize: 15 }}>ASTRAEA<em>.</em></Link>
          <Link href="/" className="label" style={{ color: "var(--ink-50)" }}>← home</Link>
        </div>
        <h1 className="display manifesto">
          Agents that do the <em>work of humans</em> — watched, approved and remembered.
        </h1>
        <div>
          <p className="label">v0.3.0 · full platform — data stays on this machine</p>
          <p className="label" style={{ marginTop: 6 }}>
            medic · operator · shield · vaani · forge · model-forge
          </p>
        </div>
      </section>

      <section className="login-right">
        <div className="login-card">
          <div className="tabs">
            <button className={mode === "login" ? "on" : ""} onClick={() => setMode("login")}>
              Sign in
            </button>
            <button className={mode === "register" ? "on" : ""} onClick={() => setMode("register")}>
              Create account
            </button>
          </div>

          <form onSubmit={submit}>
            {mode === "register" && (
              <div className="field">
                <span className="label">full name</span>
                <input
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  placeholder="Umang Vijay"
                  required
                  minLength={1}
                />
              </div>
            )}
            <div className="field">
              <span className="label">email</span>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@work.dev"
                required
              />
            </div>
            <div className="field">
              <span className="label">password</span>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={mode === "register" ? "min 8 characters" : "••••••••"}
                required
                minLength={mode === "register" ? 8 : 1}
              />
            </div>

            {error && <div className="err">✕ {error}</div>}

            <button className="btn btn--accent" disabled={busy} style={{ width: "100%" }}>
              {busy ? "working…" : mode === "login" ? "Enter console →" : "Create account →"}
            </button>
          </form>

          <button className="btn btn--ghost" disabled={busy} onClick={guest} style={{ width: "100%", marginTop: 6 }}>
            Or continue as guest (30 min) →
          </button>
          <p className="label" style={{ marginTop: 18, lineHeight: 1.8 }}>
            registering creates your personal workspace — every module you use
            <br />
            later will already know you. that is the loom promise.
          </p>
        </div>
      </section>
    </div>
    </>
  );
}
