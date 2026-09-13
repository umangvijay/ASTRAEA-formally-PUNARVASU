"use client";

import { FormEvent, useEffect, useState } from "react";
import { api } from "@/lib/api";

type Workspace = { mode: string; solo_module: string | null; modules: Record<string, boolean> };
type Profile = { company?: string; stack?: string; notes?: string };
type Matrix = Record<string, boolean>;
type VaultItem = { id: string; name: string; created_at: string };
type AuditEvent = { id: number; ts: string; action: string; detail: string; ip: string | null };
type ApiKey = { api_key_masked: string | null; configured: boolean };

const TABS = ["workspace", "profile", "sharing", "vault", "security"] as const;
type Tab = (typeof TABS)[number];

export default function SettingsPage() {
  const [tab, setTab] = useState<Tab>("workspace");
  const [ws, setWs] = useState<Workspace | null>(null);
  const [profile, setProfile] = useState<Profile>({});
  const [matrix, setMatrix] = useState<Matrix>({});
  const [vaultItems, setVaultItems] = useState<VaultItem[]>([]);
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const [apiKey, setApiKey] = useState<ApiKey | null>(null);
  const [note, setNote] = useState<string | null>(null);

  // vault form
  const [vName, setVName] = useState("");
  const [vSecret, setVSecret] = useState("");
  const [revealed, setRevealed] = useState<{ id: string; value: string } | null>(null);

  async function load() {
    const fail = (err: unknown) => setNote(err instanceof Error ? err.message : "settings load failed");
    api<Workspace>("/api/workspace").then(setWs).catch(fail);
    api<{ profile: Profile }>("/api/loom/profile").then((p) => setProfile(p.profile)).catch(fail);
    api<{ matrix: Matrix }>("/api/loom/sharing").then((m) => setMatrix(m.matrix)).catch(fail);
    api<{ items: VaultItem[] }>("/api/vault").then((v) => setVaultItems(v.items)).catch(fail);
    api<{ events: AuditEvent[] }>("/api/security/audit").then((a) => setAuditEvents(a.events)).catch(fail);
    api<ApiKey>("/api/tenants/me/api-key").then(setApiKey).catch(fail);
  }
  useEffect(() => { load(); }, []);
  useEffect(() => {
    const q = new URLSearchParams(window.location.search).get("tab");
    if (q && (TABS as readonly string[]).includes(q)) setTab(q as Tab);
  }, []);

  async function setMode(mode: "fusion" | "solo", module?: string) {
    setNote(null);
    try {
      const r = await api<Workspace>("/api/workspace", {
        method: "PUT", body: JSON.stringify({ mode, module }),
      });
      setWs(r);
      setNote(mode === "fusion"
        ? "FUSION — every module's agents are active. Memory stays shared."
        : `SOLO — only ${module} runs. Everything it and the others learned stays available.`);
    } catch (err) {
      setNote(err instanceof Error ? err.message : "failed");
    }
  }

  async function saveProfile(e: FormEvent) {
    e.preventDefault();
    await api("/api/loom/profile", { method: "PUT", body: JSON.stringify({ content: profile }) });
    setNote("profile saved — every module reads it.");
  }

  async function toggleShare(module: string) {
    const r = await api<{ matrix: Matrix }>("/api/loom/sharing", {
      method: "PATCH", body: JSON.stringify({ module, may_read: !matrix[module] }),
    });
    setMatrix(r.matrix);
  }

  async function storeSecret(e: FormEvent) {
    e.preventDefault();
    try {
      await api("/api/vault", { method: "POST", body: JSON.stringify({ name: vName, secret: vSecret }) });
      setVName(""); setVSecret("");
      setNote("secret stored — AES-256-GCM encrypted at rest.");
      load();
    } catch (err) {
      setNote(err instanceof Error ? err.message : "failed");
    }
  }

  async function reveal(id: string) {
    try {
      const r = await api<{ secret: string }>(`/api/vault/${id}/reveal`, { method: "POST" });
      setRevealed({ id, value: r.secret });
      load();
    } catch (err) {
      setNote(err instanceof Error ? err.message : "failed");
    }
  }

  async function rotateKey() {
    const r = await api<{ api_key: string }>("/api/tenants/me/api-key", { method: "POST" });
    setNote(`new API key (shown once): ${r.api_key}`);
    load();
  }

  return (
    <>
      <div className="pagehead">
        <span className="label">settings · workspace, memory sharing, secrets, security</span>
        <h1 className="display">Settings.</h1>
      </div>

      <div className="tabs" style={{ marginBottom: 20 }}>
        {TABS.map((t) => (
          <button key={t} className={tab === t ? "on" : ""} onClick={() => { setTab(t); setNote(null); setRevealed(null); }}>
            {t}
          </button>
        ))}
      </div>
      {note && <div className="glass-card" style={{ marginBottom: 18, padding: "10px 16px" }}><span className="label">{note}</span></div>}

      {/* ── Workspace tab ── */}
      {tab === "workspace" && ws && (
        <div className="grid">
          <div className="glass-card" style={{ padding: 20 }}>
            <p className="label label--ink">mode — which agents run for you</p>
            <div style={{ marginTop: 14 }}>
              <button
                className={`btn ${ws.mode === "fusion" ? "btn--accent" : "btn--ghost"}`}
                onClick={() => setMode("fusion")}
                style={{ width: "100%" }}
              >
                FUSION — all modules active
              </button>
            </div>
            <p className="label" style={{ marginTop: 10, lineHeight: 1.7 }}>
              every product agent runs; cross-module workflows allowed
            </p>
          </div>
          <div className="glass-card" style={{ padding: 20 }}>
            <p className="label label--ink">…or run ONE module (solo)</p>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 14 }}>
              {Object.entries(ws.modules).map(([m, active]) => (
                <button key={m} className={`btn ${ws.mode === "solo" && active ? "btn--accent" : "btn--ghost"}`}
                        style={{ fontSize: 11 }} onClick={() => setMode("solo", m)}>
                  {m}
                </button>
              ))}
            </div>
            <p className="label" style={{ marginTop: 12, lineHeight: 1.7 }}>
              memory is shared in every mode — switching later keeps everything learned
            </p>
          </div>
        </div>
      )}

      {/* ── Profile tab ── */}
      {tab === "profile" && (
        <div className="glass-card" style={{ maxWidth: 640, padding: 22 }}>
          <p className="label label--ink">org profile — fill once, every module reads it</p>
          <form onSubmit={saveProfile} style={{ marginTop: 10 }}>
            <div className="field"><span className="label">company</span>
              <input value={profile.company ?? ""} onChange={(e) => setProfile({ ...profile, company: e.target.value })} /></div>
            <div className="field"><span className="label">stack / services (comma separated)</span>
              <input value={profile.stack ?? ""} onChange={(e) => setProfile({ ...profile, stack: e.target.value })}
                     placeholder="fastapi, postgres, docker" /></div>
            <div className="field"><span className="label">notes / compliance</span>
              <input value={profile.notes ?? ""} onChange={(e) => setProfile({ ...profile, notes: e.target.value })}
                     placeholder="DPDP-2023, data stays in India" /></div>
            <button className="btn">Save profile →</button>
          </form>
        </div>
      )}

      {/* ── Sharing tab ── */}
      {tab === "sharing" && (
        <div className="glass-card" style={{ maxWidth: 640, padding: 22 }}>
          <p className="label label--ink">sharing matrix — who may read shared memory</p>
          <div style={{ marginTop: 10 }}>
            {Object.entries(matrix).map(([module, may]) => (
              <div key={module} style={{ display: "flex", justifyContent: "space-between", alignItems: "center",
                                         padding: "10px 0", borderBottom: "1px dotted var(--line)" }}>
                <span className="mono" style={{ fontSize: 13 }}>{module}</span>
                <button className={`btn ${may ? "btn--accent" : "btn--ghost"}`}
                        style={{ padding: "3px 12px", fontSize: 10 }}
                        onClick={() => toggleShare(module)}>
                  {may ? "SHARED" : "REVOKED"}
                </button>
              </div>
            ))}
          </div>
          <p className="label" style={{ marginTop: 12, lineHeight: 1.7 }}>
            revoke a module and its memory reads return nothing — the data stays yours
          </p>
        </div>
      )}

      {/* ── Vault tab ── */}
      {tab === "vault" && (
        <>
          <div className="glass-card" style={{ maxWidth: 640, marginBottom: 20, padding: 22 }}>
            <p className="label label--ink">secrets — AES-256-GCM encrypted at rest</p>
            <form onSubmit={storeSecret} style={{ display: "flex", gap: 10, marginTop: 10, flexWrap: "wrap", alignItems: "end" }}>
              <div className="field" style={{ marginBottom: 0, minWidth: 180 }}>
                <span className="label">name</span>
                <input value={vName} onChange={(e) => setVName(e.target.value)} required placeholder="github-token" />
              </div>
              <div className="field" style={{ marginBottom: 0, flex: 1, minWidth: 220 }}>
                <span className="label">secret (encrypted before it touches the disk)</span>
                <input value={vSecret} onChange={(e) => setVSecret(e.target.value)} required type="password" />
              </div>
              <button className="btn btn--accent">Encrypt + store →</button>
            </form>
          </div>
          <div style={{ maxWidth: 640 }}>
            {vaultItems.length === 0 && <div className="empty">no secrets yet</div>}
            {vaultItems.map((v) => (
              <div key={v.id} className="glass-card" style={{ padding: "10px 16px", marginBottom: 8, display: "flex",
                                                              gap: 12, alignItems: "center" }}>
                <span className="mono" style={{ fontSize: 13, flex: 1 }}>{v.name}</span>
                <span className="label" style={{ color: "var(--ink-30)" }}>{v.created_at?.slice(0, 10)}</span>
                <button className="btn btn--ghost" style={{ padding: "3px 10px", fontSize: 10 }} onClick={() => reveal(v.id)}>
                  REVEAL
                </button>
              </div>
            ))}
            {revealed && (
              <div className="glass-card" style={{ marginTop: 10, borderColor: "var(--accent)", padding: 16 }}>
                <p className="label label--accent">decrypted (this reveal is in your audit log)</p>
                <pre className="mono" style={{ margin: "6px 0 0", fontSize: 12.5, whiteSpace: "pre-wrap",
                                              background: "var(--paper-dim)", padding: 10 }}>
                  {revealed.value}
                </pre>
              </div>
            )}
          </div>
        </>
      )}

      {/* ── Security tab ── */}
      {tab === "security" && (
        <>
          <div className="glass-card" style={{ maxWidth: 640, marginBottom: 20, padding: 22 }}>
            <p className="label label--ink">tenant API key (for SENTINEL proxy calls)</p>
            <p className="mono" style={{ fontSize: 13, marginTop: 8 }}>
              {apiKey?.configured ? apiKey.api_key_masked : "none configured"}
            </p>
            <button className="btn" style={{ marginTop: 10 }} onClick={rotateKey}>Rotate key →</button>
          </div>
          <div className="glass-card" style={{ maxWidth: 640, padding: 22 }}>
            <p className="label label--ink">security audit trail — every login, reveal, approval</p>
            <div style={{ marginTop: 8, maxHeight: 320, overflowY: "auto" }}>
              {auditEvents.length === 0 && <div className="empty">no events yet</div>}
              {auditEvents.map((a) => (
                <div key={a.id} className="timeline-item" style={{ padding: "6px 0" }}>
                  <span className="t-ts" style={{ minWidth: 120 }}>{a.ts.slice(0, 19)}</span>
                  <span style={{ minWidth: 120, color: "var(--accent)", fontFamily: "var(--font-mono)", fontSize: 12 }}>{a.action}</span>
                  <span className="t-detail" style={{ flex: 1 }}>{a.detail}</span>
                  <span style={{ color: "var(--ink-30)", fontFamily: "var(--font-mono)", fontSize: 11 }}>{a.ip ?? ""}</span>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </>
  );
}
