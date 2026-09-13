"use client";

import { FormEvent, useEffect, useState } from "react";
import { PublicNav } from "@/components/PublicNav";
import { getToken, resolveApiBase } from "@/lib/api";

type Post = { id: string; title: string; summary: string; body: string; tags: string[]; author: string; created_at: string };

export default function Blog() {
  const [posts, setPosts] = useState<Post[]>([]);
  const [writing, setWriting] = useState(false);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [tags, setTags] = useState("");
  const [error, setError] = useState<string | null>(null);
  // Start `false` on both server and first client render to avoid a hydration
  // mismatch; resolve the real auth state after mount (bug #3).
  const [signedIn, setSignedIn] = useState(false);

  async function load() {
    try {
      const base = await resolveApiBase();
      const r = await fetch(`${base}/api/blog`);
      setPosts((await r.json()).posts);
    } catch { /* offline */ }
  }
  useEffect(() => {
    setSignedIn(!!getToken());
    load();
  }, []);

  async function publish(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const base = await resolveApiBase();
      const r = await fetch(`${base}/api/blog`, {
        method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` },
        body: JSON.stringify({ title, body, tags: tags.split(",").map((t) => t.trim()).filter(Boolean) }),
      });
      if (!r.ok) {
        const b = await r.json().catch(() => ({ detail: "failed" }));
        const d = b.detail;
        throw new Error(
          typeof d === "string"
            ? d
            : Array.isArray(d)
              ? d.map((x: { msg?: string }) => x?.msg ?? String(x)).join("; ")
              : "failed",
        );
      }
      setWriting(false); setTitle(""); setBody(""); setTags("");
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "failed");
    }
  }

  return (
    <>
      <PublicNav />
      <section className="hero">
        <div className="observatory-plaque">
          <span className="label label--accent">BLOG</span>
          <h1 className="display" style={{ marginTop: 12 }}>Stories from the crew.</h1>
          <p className="lead">Write about your experience with the agents, share automations, teach the community. Sign in to publish.</p>
        </div>
      </section>
      <section className="section" style={{ paddingTop: 10 }}>
        {signedIn && !writing && (
          <button className="btn btn--accent" onClick={() => setWriting(true)} style={{ marginBottom: 24 }}>✍ Write a post</button>
        )}
        {!signedIn && (
          <div className="empty" style={{ marginBottom: 24 }}>
            sign in from the console to write posts — Google OAuth sign-in is coming.
          </div>
        )}
        {writing && (
          <form onSubmit={publish} className="panel glass" style={{ marginBottom: 26 }}>
            <div className="field"><span className="label">title</span>
              <input value={title} onChange={(e) => setTitle(e.target.value)} required minLength={5} placeholder="How MEDIC saved my production database" /></div>
            <div className="field"><span className="label">body (markdown-ish, min 20 chars)</span>
              <textarea value={body} onChange={(e) => setBody(e.target.value)} required minLength={20} rows={8}
                        style={{ width: "100%", background: "transparent", border: "1px solid var(--line)", padding: 12, color: "var(--ink)", fontFamily: "var(--font-mono)", fontSize: 13, resize: "vertical" }} /></div>
            <div className="field"><span className="label">tags (comma-separated)</span>
              <input value={tags} onChange={(e) => setTags(e.target.value)} placeholder="medic, sre, automation" /></div>
            {error && <div className="err">✕ {error}</div>}
            <div style={{ display: "flex", gap: 10 }}>
              <button className="btn btn--accent" type="submit">Publish →</button>
              <button className="btn btn--ghost" type="button" onClick={() => setWriting(false)}>Cancel</button>
            </div>
          </form>
        )}
        {posts.length === 0 && !writing && <div className="empty">no posts yet — be the first to write.</div>}
        {posts.map((p) => (
          <div key={p.id} className="panel glass" style={{ marginBottom: 14 }}>
            <span className="label">{p.author} · {p.created_at.slice(0, 10)}</span>
            <h3 style={{ margin: "6px 0 4px", fontSize: 19 }}>{p.title}</h3>
            <p style={{ fontSize: 13.5, color: "var(--ink-70)", margin: 0 }}>{p.summary}</p>
            <details style={{ marginTop: 8 }}><summary className="label">read more →</summary>
              <p style={{ fontSize: 13.5, whiteSpace: "pre-wrap", marginTop: 8 }}>{p.body}</p></details>
          </div>
        ))}
      </section>
      <footer className="site-footer">
        <span className="label">© 2026 Astraea</span>
      </footer>
    </>
  );
}
