"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { api, clearToken, getToken, MODULES } from "@/lib/api";
import { ThemeToggle } from "@/components/ThemeToggle";

type Me = { user: { email: string; full_name: string; tenant: { name: string } } };
type ModulesResp = { active_profile: string; mode: string; version?: string; phase?: number };
type LoomItem = { id: string; kind: string; title: string; origin_module: string; created_at: string };
type SelfTest = { status: string; degraded: string[] };
type Workspace = { mode: string; solo_module: string | null };

const NAV: { group: string; links: { href: string; label: string; match: (p: string) => boolean }[] }[] = [
  {
    group: "work",
    links: [
      { href: "/console", label: "Overview", match: (p) => p === "/console" },
      { href: "/console/fusion", label: "Fusion", match: (p) => p.startsWith("/console/fusion") },
      { href: "/console/chat", label: "Chat", match: (p) => p.startsWith("/console/chat") },
      { href: "/console/runs", label: "Runs", match: (p) => p.startsWith("/console/runs") },
    ],
  },
  {
    group: "platform",
    links: [
      { href: "/console/sentinel", label: "Sentinel", match: (p) => p.startsWith("/console/sentinel") },
      { href: "/console/loom", label: "Memory", match: (p) => p.startsWith("/console/loom") },
      { href: "/console/settings", label: "Settings", match: (p) => p.startsWith("/console/settings") },
    ],
  },
];

export default function ConsoleLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [me, setMe] = useState<Me | null>(null);
  const [sys, setSys] = useState<ModulesResp | null>(null);
  const [loom, setLoom] = useState<LoomItem[]>([]);
  const [selftest, setSelftest] = useState<SelfTest | null>(null);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [checked, setChecked] = useState(false);
  const [bootError, setBootError] = useState<string | null>(null);

  useEffect(() => {
    if (!getToken()) {
      setChecked(true);
      router.replace("/login");
      return;
    }
    const fail = (err: unknown) => {
      setBootError(err instanceof Error ? err.message : "API unreachable");
    };
    api<Me>("/api/auth/me")
      .then((m) => { setMe(m); setBootError(null); })
      .catch(fail)
      .finally(() => setChecked(true));
    api<ModulesResp>("/api/modules").then(setSys).catch(fail);
    api<{ items: LoomItem[] }>("/api/loom/items")
      .then((r) => setLoom(r.items.slice(0, 3)))
      .catch(fail);
    api<SelfTest>("/api/system/selftest").then(setSelftest).catch(fail);
    api<Workspace>("/api/workspace").then(setWorkspace).catch(fail);
    const t = setInterval(() => {
      api<SelfTest>("/api/system/selftest").then(setSelftest).catch(fail);
    }, 30000);
    return () => clearInterval(t);
  }, [router]);

  useEffect(() => {
    document.querySelectorAll(".bar-menu[open]").forEach((el) => el.removeAttribute("open"));
  }, [pathname]);

  if (!checked) {
    return (
      <>
        <main style={{ display: "flex", minHeight: "100vh", alignItems: "center", justifyContent: "center" }}>
          <p className="label">opening console…</p>
        </main>
        {/* Keep the RSC child mounted so server notFound() can return HTTP 404. */}
        <div hidden>{children}</div>
      </>
    );
  }

  function logout() {
    clearToken();
    router.replace("/login");
  }

  const healthy = selftest?.status === "healthy";

  return (
    <>
      <header className="commandbar">
        <Link href="/console" className="wordmark">
          ASTRAEA<em>.</em>
        </Link>
        <details className="bar-menu">
          <summary>Menu</summary>
          <div className="bar-menu-panel">
            {NAV.flatMap((g) => g.links).map((l) => (
              <Link key={l.href} href={l.href} className={l.match(pathname) ? "active" : ""}>
                {l.label}
              </Link>
            ))}
            <p className="label label--accent" style={{ margin: "12px 12px 6px" }}>Agents</p>
            {MODULES.map((m) => (
              <Link key={m.codename} href={`/console/${m.codename}`}
                    className={pathname === `/console/${m.codename}` ? "active" : ""}>
                {m.name}
              </Link>
            ))}
          </div>
        </details>
        <nav className="commandbar-nav">
          {NAV.map((g) => (
            <span key={g.group} className="nav-group">
              {g.links.map((l) => (
                <Link key={l.href} href={l.href} className={l.match(pathname) ? "active" : ""}>
                  {l.label}
                </Link>
              ))}
              <i className="nav-sep" aria-hidden />
            </span>
          ))}
          <details className="nav-drop">
            <summary className={pathname.match(/^\/console\/(medic|operator|shield|vaani|forge|model_forge)/) ? "active" : ""}>
              Agents ▾
            </summary>
            <div className="drop-panel">
              {MODULES.map((m) => (
                <Link key={m.codename} href={`/console/${m.codename}`}
                      className={pathname === `/console/${m.codename}` ? "active" : ""}>
                  <b>{m.name}</b>
                  <span>{m.title}</span>
                </Link>
              ))}
            </div>
          </details>
        </nav>
        <div className="commandbar-end">
          {workspace && (
            <Link href="/console/settings"
                  className="mode-chip"
                  title="switch SOLO/FUSION in Settings">
              <span className={`dot ${workspace.mode === "fusion" ? "dot--live" : "dot--amber"}`} />
              {workspace.mode === "fusion" ? "FUSION · all modules" : `SOLO · ${workspace.solo_module ?? "?"}`}
            </Link>
          )}
          <span className={`selftest-chip ${selftest ? (healthy ? "ok" : "warn") : ""}`}
                title={selftest?.degraded?.join(", ") || "all smoke paths green"}>
            <span className={`dot ${healthy ? "dot--live" : selftest ? "dot--amber" : ""}`} />
            {selftest ? (healthy ? "all systems ok" : `degraded: ${selftest.degraded.length}`) : "…"}
          </span>
          {me && <span className="label label--ink">{me.user.email}</span>}
          <ThemeToggle />
          <button className="btn btn--ghost" style={{ padding: "5px 12px" }} onClick={logout}>
            Exit
          </button>
        </div>
      </header>

      {bootError && (
        <div className="glass-card" style={{ margin: "10px 18px 0", padding: "10px 14px" }}>
          <span className="label label--accent">API ERROR</span>
          <p style={{ margin: "4px 0 0", fontSize: 13 }}>{bootError}</p>
        </div>
      )}
      <div className="shell">
        <main className="main">{children}</main>
        <aside className="rail">
          <div>
            <p className="label label--accent">SHARED MEMORY · WHAT THEY LEARNED</p>
            {loom.length === 0 ? (
              <div className="empty" style={{ marginTop: 10 }}>
                nothing yet — when your agents work, everything they learn lands here.
              </div>
            ) : (
              loom.map((item) => (
                <Link key={item.id} href="/console/loom" className="rail-item">
                  <span className={`stamp stamp--from-${item.origin_module}`}>FROM {item.origin_module.toUpperCase()}</span>
                  <span className="rail-item-title">{item.title}</span>
                </Link>
              ))
            )}
          </div>
          <div className="panel">
            <p className="label label--ink">session</p>
            <div style={{ marginTop: 8 }}>
              <div className="kv"><span className="k">workspace</span><span className="v">{me?.user.tenant.name ?? "—"}</span></div>
              <div className="kv"><span className="k">storage</span><span className="v">{sys?.mode ?? "—"}</span></div>
              <div className="kv"><span className="k">profile</span><span className="v">{sys?.active_profile ?? "full"}</span></div>
              <div className="kv"><span className="k">platform</span><span className="v">v{sys?.version ?? "—"} · phase {sys?.phase ?? "—"}</span></div>
            </div>
          </div>
          <p className="label" style={{ lineHeight: 1.8 }}>
            spec → docs/MASTER_SPEC.md<br />
            ops → docs/RUNBOOK.md
          </p>
        </aside>
      </div>
    </>
  );
}
