"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { CORE_SERVICES, MODULES, api } from "@/lib/api";
import { PageError } from "@/components/PageError";
import { PLATES } from "@/lib/plates";

type ModulesResp = { modules: { codename: string; status: string }[] };
type SelfTest = { status: string; degraded: string[]; checks: Record<string, { ok: boolean; detail: string }> };
type Stats = { runs: number; anomalies: number; incidents: number; tokens_used: number };

const PLATE_SRC: Record<string, string> = Object.fromEntries(
  PLATES.map((p) => [p.id === "astraea" ? "model_forge" : p.id, p.image]),
);

const CORE_LINKS = [
  { href: "/console/fusion", name: "Fusion", blurb: "Every agent on one live board." },
  { href: "/console/chat", name: "Chat", blurb: "Talk through SENTINEL — never the SQL champ." },
  { href: "/console/runs", name: "Runs", blurb: "Jobs that survive crashes." },
  { href: "/console/loom", name: "Memory", blurb: "Provenance-stamped notebook." },
  { href: "/console/sentinel", name: "SENTINEL", blurb: "Every model call is scanned." },
  { href: "/console/settings", name: "Settings · Vault", blurb: "Modes, Argon2id secrets, audit." },
];

export default function OverviewPage() {
  const [registry, setRegistry] = useState<ModulesResp | null>(null);
  const [selftest, setSelftest] = useState<SelfTest | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [guideOpen, setGuideOpen] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    const fail = (e: unknown) => setErr(e instanceof Error ? e.message : "API failed");
    api<ModulesResp>("/api/modules").then(setRegistry).catch(fail);
    api<SelfTest>("/api/system/selftest").then(setSelftest).catch(fail);
    (async () => {
      try {
        const [runs, anomalies, incidents, sentinel] = await Promise.all([
          api<{ runs: unknown[] }>("/api/runs?limit=100"),
          api<{ anomalies: unknown[] }>("/api/pulse/anomalies"),
          api<{ incidents: unknown[] }>("/api/shield/incidents"),
          api<{ quota: { tokens_used: number } }>("/api/sentinel/stats"),
        ]);
        setStats({
          runs: runs.runs.length,
          anomalies: anomalies.anomalies.length,
          incidents: incidents.incidents.length,
          tokens_used: sentinel.quota.tokens_used,
        });
      } catch {
        /* stats are decorative; pages show their own errors */
      }
    })();
  }, []);

  const statusOf = (codename: string) => {
    if (!selftest) return "…";
    if (selftest.status === "healthy") return "up";
    const modulecheck: Record<string, string> = {
      medic: "pulse_detector",
      shield: "shield_detector",
      forge: "forge_consolidator",
      model_forge: "llm_provider",
    };
    const check = modulecheck[codename];
    if (check && selftest.checks[check]) return selftest.checks[check].ok ? "up" : "degraded";
    if (codename === "medic" && selftest.checks.telemetry_stream && !selftest.checks.telemetry_stream.ok) {
      return "degraded";
    }
    return "…";
  };

  return (
    <>
      <div className="pagehead">
        <span className="label label--accent">◈ observatory · command overview</span>
        <h1 className="display">Good day, operator.</h1>
        <p>
          Six workbenches share SENTINEL, Runs and Memory. This is a lab control
          plane — not six funded products. Open Fusion to run them together.
        </p>
      </div>
      <PageError message={err} />

      <div className="instrument-grid">
        <div className="instrument glass-card">
          <p className="inst-label">agent runs</p>
          <div className="inst-value">{stats?.runs ?? "—"}</div>
          <p className="inst-trend">total executed</p>
        </div>
        <div className="instrument glass-card">
          <p className="inst-label">anomalies caught</p>
          <div className="inst-value inst-value--accent">{stats?.anomalies ?? "—"}</div>
          <p className="inst-trend">by MEDIC</p>
        </div>
        <div className="instrument glass-card">
          <p className="inst-label">security incidents</p>
          <div className="inst-value">{stats?.incidents ?? "—"}</div>
          <p className="inst-trend">by SHIELD</p>
        </div>
        <div className="instrument glass-card">
          <p className="inst-label">llm tokens (month)</p>
          <div className="inst-value">{stats?.tokens_used != null ? stats.tokens_used.toLocaleString() : "—"}</div>
          <p className="inst-trend">through SENTINEL</p>
        </div>
        <div className="instrument glass-card">
          <p className="inst-label">platform</p>
          <div className="inst-value" style={{ fontSize: 14, paddingTop: 4 }}>
            <span className={`dot ${selftest?.status === "healthy" ? "dot--live" : selftest ? "dot--amber" : ""}`} />{" "}
            {selftest ? selftest.status : "checking…"}
          </div>
          <p className="inst-trend">
            {selftest?.status === "healthy"
              ? "all systems operational"
              : selftest?.degraded?.length
                ? `${selftest.degraded.length} degraded`
                : "checking…"}
          </p>
        </div>
      </div>

      <div style={{ marginBottom: 26 }}>
        <button
          className="collapsible-trigger"
          onClick={() => setGuideOpen(!guideOpen)}
        >
          {guideOpen ? "▾ Hide guide" : "▸ First time? How this works — 60 seconds"}
        </button>
        <div className={`collapsible-content ${guideOpen ? "open" : ""}`}>
          <div className="panel glass" style={{ padding: 20 }}>
            <div className="guide-grid">
              <div className="guide-step">
                <span className="guide-no">1</span>
                <div>
                  <p style={{ margin: "0 0 3px", fontWeight: 600, fontSize: 13.5 }}>Pick an agent</p>
                  <p style={{ margin: 0, fontSize: 12.5, color: "var(--ink-70)" }}>
                    MEDIC watches your services, SHIELD guards your network, OPERATOR works websites,
                    VAANI takes calls. Open any from <b>Agents ▾</b> above.
                  </p>
                </div>
              </div>
              <div className="guide-step">
                <span className="guide-no">2</span>
                <div>
                  <p style={{ margin: "0 0 3px", fontWeight: 600, fontSize: 13.5 }}>Let it work</p>
                  <p style={{ margin: 0, fontSize: 12.5, color: "var(--ink-70)" }}>
                    Everything appears live in <b>Fusion</b>. Jobs are recorded in <b>Runs</b> and
                    survive crashes.
                  </p>
                </div>
              </div>
              <div className="guide-step">
                <span className="guide-no">3</span>
                <div>
                  <p style={{ margin: "0 0 3px", fontWeight: 600, fontSize: 13.5 }}>Approve the risky parts</p>
                  <p style={{ margin: 0, fontSize: 12.5, color: "var(--ink-70)" }}>
                    Before an agent applies a fix or contains an attack it pauses and asks you —
                    flagged as <b>⚑ needs your decision</b>.
                  </p>
                </div>
              </div>
              <div className="guide-step">
                <span className="guide-no">4</span>
                <div>
                  <p style={{ margin: "0 0 3px", fontWeight: 600, fontSize: 13.5 }}>It remembers everything</p>
                  <p style={{ margin: 0, fontSize: 12.5, color: "var(--ink-70)" }}>
                    Every lesson is shared (<b>Memory</b>) — switch agents any time, nothing is
                    re-entered. Secrets live encrypted in <b>Settings → Vault</b>.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <section>
        <p className="label label--ink" style={{ marginBottom: 12 }}>THE CONSTELLATION — six workbenches</p>
        <div className="grid">
          {MODULES.map((m) => {
            const st = statusOf(m.codename);
            const plate = PLATE_SRC[m.codename];
            return (
              <Link key={m.codename} href={`/console/${m.codename}`} className="glass-card module-card">
                {plate && <img className="module-plate" src={plate} alt="" />}
                <div className="head">
                  <span className="label">{m.codename} · profile: {m.profile}</span>
                  <span>
                    <span className={`dot ${st === "up" ? "dot--live" : st === "degraded" ? "dot--amber" : ""}`} />
                  </span>
                </div>
                <div className="body">
                  <h3 className="display">{m.name}</h3>
                  <p className="label" style={{ margin: "0 0 8px" }}>{m.title}</p>
                  <p className="blurb clamp3">{m.blurb}</p>
                </div>
                <div className="foot">
                  <span className="stamp stamp--phase">PHASE {m.phase}</span>
                  <span className="label">open workbench →</span>
                </div>
              </Link>
            );
          })}
        </div>
      </section>

      <section style={{ marginTop: 34 }}>
        <div className="glass-card panel--accent" style={{ padding: 22 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 22, flexWrap: "wrap" }}>
            <div style={{ flex: 1, minWidth: 260 }}>
              <p className="label label--accent">◈ mission control · every agent on one screen</p>
              <h2 className="display" style={{ margin: "6px 0 4px", fontSize: 24 }}>Fusion</h2>
              <p style={{ margin: 0, fontSize: 13.5, color: "var(--ink-70)" }}>
                The live feed of everything your agents are doing — and everything waiting for your decision.
              </p>
            </div>
            <Link href="/console/fusion" className="btn btn--accent">Open Fusion →</Link>
          </div>
        </div>
      </section>

      <section style={{ marginTop: 30 }}>
        <p className="label label--ink" style={{ marginBottom: 12 }}>ALWAYS ON — click to open</p>
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
          {CORE_LINKS.map((s) => (
            <Link key={s.href} href={s.href} className="glass-card" style={{ flex: "1 1 200px", padding: 16 }}>
              <p className="label label--accent" style={{ margin: "0 0 4px" }}>{s.name}</p>
              <p className="clamp2" style={{ fontSize: 12, color: "var(--ink-70)", margin: 0 }}>{s.blurb}</p>
            </Link>
          ))}
        </div>
        <p className="label" style={{ marginTop: 14 }}>
          also running: {CORE_SERVICES.map((s) => s.name).join(" · ")}
          {registry ? ` · ${registry.modules.length} modules registered` : ""}
        </p>
      </section>
    </>
  );
}
