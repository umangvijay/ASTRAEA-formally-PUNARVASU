"use client";

import { useEffect, useState } from "react";
import { CORE_SERVICES, MODULES, api, type ModuleMeta } from "@/lib/api";

type Sys = { active_profile: string; mode: string };

export default function ModuleWorkbench({ codename }: { codename: string }) {
  const meta = MODULES.find((m) => m.codename === codename) as ModuleMeta;
  const [sys, setSys] = useState<Sys | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Sys>("/api/modules")
      .then((s) => { setSys(s); setError(null); })
      .catch((err) => setError(err instanceof Error ? err.message : "modules failed"));
  }, []);

  return (
    <>
      <div className="pagehead">
        <span className="stamp" style={{ marginBottom: 10 }}>SOLO MODE</span>{" "}
        <span className="stamp stamp--phase" style={{ marginBottom: 10 }}>PHASE {meta.phase}</span>{" "}
        <span className="stamp stamp--local" style={{ marginBottom: 10 }}>PROFILE: {meta.profile}</span>
        <h1 className="display">{meta.name}</h1>
        <p>
          <b>{meta.title}.</b> {meta.blurb}
        </p>
      </div>

      {error && (
        <div className="glass-card" style={{ padding: "10px 14px", marginBottom: 16 }}>
          <span className="label label--accent">API ERROR</span>
          <p style={{ margin: "4px 0 0", fontSize: 13 }}>{error}</p>
        </div>
      )}

      <div className="grid">
        <div className="panel">
          <p className="label label--ink">status</p>
          <div style={{ marginTop: 10 }}>
            <div className="kv"><span className="k">module</span><span className="v"><span className="dot dot--amber" /> lands in phase {meta.phase}</span></div>
            <div className="kv"><span className="k">runtime mode</span><span className="v">{sys?.mode ?? "…"}</span></div>
            <div className="kv"><span className="k">active profile</span><span className="v">{sys?.active_profile ?? "…"}</span></div>
            <div className="kv"><span className="k">solo boot</span><span className="v">python3 main.py --profile {meta.profile}</span></div>
          </div>
        </div>

        <div className="panel">
          <p className="label label--ink">benchmark — the scoreboard</p>
          <div style={{ marginTop: 10 }}>
            <div className="kv"><span className="k">metric</span><span className="v">{meta.benchmark}</span></div>
          </div>
          <div className="empty" style={{ marginTop: 12 }}>
            chart lands with phase {meta.phase}. a module without its
            benchmark is not done — spec §4.6.
          </div>
        </div>

        <div className="panel">
          <p className="label label--ink">tools</p>
          <div className="empty" style={{ marginTop: 10 }}>
            tool registry arrives in phase 1. every tool call will be
            sandboxed, metered, replayable — and approved where it matters.
          </div>
        </div>

        <div className="panel">
          <p className="label label--ink">shares context via loom with</p>
          <div style={{ marginTop: 12, display: "flex", flexWrap: "wrap", gap: 8 }}>
            {MODULES.filter((m) => m.codename !== meta.codename).map((m) => (
              <span key={m.codename} className="stamp stamp--shared">{m.name}</span>
            ))}
          </div>
          <p className="label" style={{ marginTop: 14, lineHeight: 1.8 }}>
            whatever you do here, the others will know — stamped, readable,
            revocable in settings.
          </p>
        </div>
      </div>

      <div className="footer-strip">
        {CORE_SERVICES.map((s) => (
          <span key={s.codename} className="label">◈ {s.name} · phase {s.phase}</span>
        ))}
      </div>
    </>
  );
}
