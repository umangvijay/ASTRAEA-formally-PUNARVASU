"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const SECTIONS: { group: string; pages: { href: string; label: string; blurb: string }[] }[] = [
  {
    group: "dashboard",
    pages: [
      { href: "/docs", label: "Start here", blurb: "observatory dashboard" },
      { href: "/docs/getting-started", label: "Getting started", blurb: "install, boot, first job" },
    ],
  },
  {
    group: "the workspace",
    pages: [
      { href: "/docs/fusion", label: "Fusion", blurb: "mission control — start & watch" },
      { href: "/docs/runs", label: "Runs", blurb: "jobs that survive crashes" },
      { href: "/docs/memory", label: "Memory (LOOM)", blurb: "what your agents remember" },
      { href: "/docs/sentinel", label: "Sentinel", blurb: "the AI security gateway" },
      { href: "/docs/settings", label: "Settings & Vault", blurb: "modes, secrets, audit trail" },
      { href: "/docs/chat", label: "Chat", blurb: "SENTINEL turns — not Fusion" },
    ],
  },
  {
    group: "the plane",
    pages: [
      { href: "/docs/architecture", label: "Architecture", blurb: "stack, data flow, pipelines" },
      { href: "/docs/security", label: "Security", blurb: "Argon2id, AES-256-GCM, SENTINEL" },
      { href: "/docs/deploy", label: "Deploy", blurb: "offline, GCloud Vertex, AWS later" },
    ],
  },
  {
    group: "the agents",
    pages: [
      { href: "/docs/medic", label: "MEDIC", blurb: "AI SRE — fixes your services" },
      { href: "/docs/shield", label: "SHIELD", blurb: "AI SOC — catches attacks" },
      { href: "/docs/operator", label: "OPERATOR", blurb: "live web + computer-use" },
      { href: "/docs/vaani", label: "VAANI", blurb: "takes voice calls & books work" },
      { href: "/docs/forge", label: "FORGE", blurb: "the self-improvement loop" },
      { href: "/docs/model-forge", label: "MODEL-FORGE", blurb: "our own trained model" },
    ],
  },
];

export function DocsNav() {
  const pathname = usePathname();
  return (
    <aside className="docs-side">
      {SECTIONS.map((s) => (
        <div key={s.group} style={{ marginBottom: 18 }}>
          <p className="label label--ink" style={{ margin: "0 0 6px" }}>{s.group.toUpperCase()}</p>
          {s.pages.map((p) => (
            <Link key={p.href} href={p.href} className={`docs-link ${pathname === p.href ? "active" : ""}`}>
              <b>{p.label}</b>
              <span>{p.blurb}</span>
            </Link>
          ))}
        </div>
      ))}
    </aside>
  );
}
