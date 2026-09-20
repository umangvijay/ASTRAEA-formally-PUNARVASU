"use client";

/**
 * SolarSystem — the Astraea sky.
 *
 * - Sun (astra-core) + 8 bodies on live orbits; each body IS a module.
 * - Click a body → feature card (what it does, its "moons" = sub-features, CTA).
 * - Drag to pan, wheel to zoom, double-click to reset. Bodies stay 3D while dragged.
 * - The galaxy backdrop rotates (we orbit the Milky Way) and the system drifts
 *   through it; the whole orbital plane slowly precesses — moving across the universe.
 * - One rAF loop, transform-only, pauses when hidden, honors prefers-reduced-motion.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { createPortal } from "react-dom";

type Moon = { name: string; note: string; size: number; dist: number; speed: number; tex: string };

type Body = {
  id: string;
  name: string;            // celestial name
  module: string;          // module codename (display)
  title: string;           // human role
  blurb: string;
  href: string;            // console workbench
  docs: string;            // docs page
  features: string[];
  benchmark: string;
  tex: string;
  size: number;            // globe px
  radius: number;          // orbit fraction of u (half min dimension)
  speed: number;           // orbital speed multiplier (kepler-ish set below)
  phase: number;           // starting angle (rad)
  ring?: boolean;
  inclined?: number;       // deg — tilts the whole orbit plane
  moons?: Moon[];
};

const M = (name: string, note: string, size = 8, dist = 1.8, speed = 2.4, tex = "/cosmos/moon.png"): Moon =>
  ({ name, note, size, dist, speed, tex });

export const BODIES: Body[] = [
  {
    id: "mercury", name: "Mercury", module: "SENTINEL", title: "The Security Gateway",
    blurb: "Swift guard closest to the core. Every AI call in the platform passes through it — injections blocked, PII redacted mid-stream.",
    href: "/console/sentinel", docs: "/docs/sentinel",
    features: ["Prompt-injection blocking", "Jailbreak patterns", "Indic-PII redaction", "Stream scanning", "Token quotas"],
    benchmark: "Scan overhead < 120 ms", tex: "/cosmos/mercury.png",
    size: 18, radius: 0.24, speed: 1.0, phase: 0.7,
  },
  {
    id: "venus", name: "Venus", module: "PULSE", title: "The Telemetry Beacon",
    blurb: "The brightest beacon: logs, metrics and traces stream through it in real time, feeding MEDIC and SHIELD from one bus.",
    href: "/console/medic", docs: "/docs/medic",
    features: ["Live metrics ingest", "Log + deploy events", "One stream for all agents"],
    benchmark: "10 s detector heartbeat", tex: "/cosmos/venus.png",
    size: 26, radius: 0.33, speed: 0.72, phase: 2.4,
  },
  {
    id: "earth", name: "Earth", module: "VAANI", title: "The Voice Employee",
    blurb: "The living world. VAANI answers calls in real time, books the work, and every booking becomes a durable record.",
    href: "/console/vaani", docs: "/docs/vaani",
    features: ["Silero VAD + faster-whisper", "Barge-in < 100 ms", "Bookings as durable runs", "Transcripts to Memory"],
    benchmark: "p95 reply < 1.5 s", tex: "/cosmos/earth.png",
    size: 28, radius: 0.43, speed: 0.55, phase: 4.1,
    moons: [M("MODEL-FORGE", "Our own trained SQL model — our closest companion, served locally", 13, 1.9, 1.8)],
  },
  {
    id: "mars", name: "Mars", module: "MEDIC", title: "The On-Call Engineer",
    blurb: "The red planet of incidents. Watches telemetry, detects drift, reproduces the fault and prepares the fix — you approve it.",
    href: "/console/medic", docs: "/docs/medic",
    features: ["Isolation-forest detection", "Root-cause ranking", "Sandbox reproduction", "Fix diffs + PRs"],
    benchmark: "MTTD 8.9 s · top-3 100%", tex: "/cosmos/mars.png",
    size: 22, radius: 0.53, speed: 0.44, phase: 5.6,
  },
  {
    id: "jupiter", name: "Jupiter", module: "SHIELD", title: "The SOC Analyst",
    blurb: "The giant with the most moons — each moon a detection family. Correlates attacks into incidents, maps MITRE ATT&CK, drafts containment.",
    href: "/console/shield", docs: "/docs/shield",
    features: ["Brute-force & spraying", "Port-scan detection", "Exfil + C2 beaconing", "Attack graphs", "Containment gate"],
    benchmark: "5/5 scenarios · 0% FP", tex: "/cosmos/jupiter.png",
    size: 52, radius: 0.66, speed: 0.34, phase: 1.2,
    moons: [
      M("T1110", "Brute force & credential attacks", 9, 1.55, 2.2),
      M("T1046", "Network service discovery", 7, 1.95, 1.6),
      M("T1041", "Exfiltration over C2", 8, 2.35, 1.25),
    ],
  },
  {
    id: "saturn", name: "Saturn", module: "LOOM", title: "The Shared Memory",
    blurb: "The ringed keeper of everything learned. Its rings are provenance — every memory carries where it was born and who used it.",
    href: "/console/loom", docs: "/docs/memory",
    features: ["Vector search (Chroma + MiniLM)", "Provenance stamps", "Sharing matrix", "RAG for every agent"],
    benchmark: "Semantic recall across all modules", tex: "/cosmos/saturn.png",
    size: 44, radius: 0.80, speed: 0.27, phase: 3.3, ring: true,
  },
  {
    id: "neptune", name: "Neptune", module: "FORGE", title: "The Self-Improvement Loop",
    blurb: "Far out in the dark, studying failures. Proposes improvements nightly; only measured wins are promoted — every champion a git commit.",
    href: "/console/forge", docs: "/docs/forge",
    features: ["Failure mining", "Verifiable SQL evals", "Champion promotion", "Week-over-week chart"],
    benchmark: "Promote only if strictly better", tex: "/cosmos/neptune.png",
    size: 30, radius: 0.93, speed: 0.22, phase: 5.9,
  },
  {
    id: "ceres", name: "Ceres", module: "OPERATOR", title: "The Computer-Use Agent",
    blurb: "A dwarf world on a tilted orbit — it goes anywhere, even where no API exists. Works websites like a person and verifies every action.",
    href: "/console/operator", docs: "/docs/operator",
    features: ["Set-of-Mark grounding", "Vision → fallback chain", "Screenshot-diff verify", "Trajectory replay"],
    benchmark: "80–85% on 20-task suite", tex: "/cosmos/moon.png",
    size: 16, radius: 0.585, speed: 0.5, phase: 2.0, inclined: -14,
  },
];

const SUN = {
  name: "Sol", module: "ASTRAEA", title: "The Core Runtime",
  blurb: "The returning light at the center. The durable event-sourced engine every agent orbits — runs survive crashes, pause for your approval, replay forever.",
  href: "/console", docs: "/docs/runs",
  features: ["Event-sourced runs", "Human approval gates", "Crash recovery", "Full replay", "Sandboxed tools"],
  benchmark: "48/48 tests · self-healing watchdog",
};

const K = 0.09; // base angular speed rad/s at radius 0.24 → mercury ~70s/rev

function position(radius: number, angle: number, u: number, squash = 0.4) {
  const r = radius * u;
  return { x: Math.cos(angle) * r, y: Math.sin(angle) * r * squash };
}

export function SolarSystem() {
  const stageRef = useRef<HTMLDivElement>(null);
  const bodyRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const sunRef = useRef<HTMLDivElement>(null);
  const [selected, setSelected] = useState<Body | null>(null);
  const [mounted, setMounted] = useState(false);
  useEffect(() => { setMounted(true); }, []);
  const [hover, setHover] = useState<string | null>(null);
  const view = useRef({ x: 0, y: 0, k: 1 });
  const drag = useRef<{ on: boolean; moved: boolean; sx: number; sy: number }>({ on: false, moved: false, sx: 0, sy: 0 });

  const reduced = useMemo(
    () => typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    []
  );

  const applyView = useCallback(() => {
    const v = view.current;
    stageRef.current?.style.setProperty("transform", `translate3d(${v.x}px, ${v.y}px, 0) scale(${v.k})`);
  }, []);

  useEffect(() => {
    let raf = 0;
    let last = performance.now();
    let t = 0;
    const tick = (now: number) => {
      raf = requestAnimationFrame(tick);
      if (document.hidden) { last = now; return; }
      const dt = Math.min((now - last) / 1000, 0.1);
      last = now;
      t += dt;
      const u = (Math.min(window.innerWidth, window.innerHeight) / 2) * 0.85;
      const precess = reduced ? 0 : t * 0.008; // plane drifts across the universe
      for (const b of BODIES) {
        const el = bodyRefs.current[b.id];
        if (!el) continue;
        const angle = reduced ? b.phase : b.phase + t * K * b.speed * (0.24 / b.radius) ** 0.5;
        const p = position(b.radius, angle, u);
        const tilt = b.inclined ?? 0;
        el.style.transform =
          `translate3d(calc(-50% + ${p.x}px), calc(-50% + ${p.y}px), 0) rotate(${tilt + Math.sin(precess) * 2}deg)`;
      }
      if (sunRef.current) {
        sunRef.current.style.transform =
          `translate3d(calc(-50% + ${reduced ? 0 : Math.sin(t * 0.05) * 6}px), calc(-50% + ${reduced ? 0 : Math.cos(t * 0.04) * 4}px), 0)`;
      }
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [reduced]);

  const onPointerDown = (e: React.PointerEvent) => {
    drag.current = { on: true, moved: false, sx: e.clientX - view.current.x, sy: e.clientY - view.current.y };
  };
  const onPointerMove = (e: React.PointerEvent) => {
    if (!drag.current.on) return;
    const dx = Math.abs(e.clientX - drag.current.sx - view.current.x);
    const dy = Math.abs(e.clientY - drag.current.sy - view.current.y);
    if (dx + dy > 6) drag.current.moved = true;
    if (drag.current.moved) {
      view.current.x = e.clientX - drag.current.sx;
      view.current.y = e.clientY - drag.current.sy;
      applyView();
    }
  };
  const onPointerUp = () => { drag.current.on = false; };
  const onWheel = (e: React.WheelEvent) => {
    const k = Math.min(1.8, Math.max(0.55, view.current.k * (e.deltaY > 0 ? 0.93 : 1.075)));
    view.current.k = k;
    applyView();
  };
  const reset = () => { view.current = { x: 0, y: 0, k: 1 }; applyView(); setSelected(null); };

  useEffect(() => {
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setSelected(null);
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, []);

  const pick = (b: Body) => (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!drag.current.moved) setSelected(b);
  };

  const card = selected;

  return (
    <>
      {/* ── sky: galaxy rotates around us; we drift through it ── */}
      <div className="cosmos" aria-hidden>
        <div className="cosmos-sky-wrap galactic-plane">
          <img className="cosmos-sky" src="/cosmos/milkyway.png" alt="" />
          <span className="cosmos-nebula nebula-rose" />
          <span className="cosmos-nebula nebula-teal" />
          <span className="cosmos-galaxy galaxy-andromeda" />
          <span className="cosmos-galaxy galaxy-pinwheel" />
          <span className="cosmos-stars" />
          <span className="cosmos-stars stars-far" />
          <span className="cosmos-stars stars-near" />
          <span className="cosmos-sky-veil" />
          <div className="cosmos-comets">
            <span className="comet comet-1" />
            <span className="comet comet-2" />
            <span className="comet comet-3" />
          </div>
        </div>
      </div>

      {/* ── the system ── */}
      <div
        className="solsys"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerLeave={onPointerUp}
        onWheel={onWheel}
        onDoubleClick={reset}
      >
        <div className="solsys-stage" ref={stageRef}>
          {/* orbit rings */}
          {BODIES.map((b) => (
            <span key={`ring-${b.id}`} className="solsys-ring" data-inclined={b.inclined ?? 0}
                  style={{ width: `${b.radius * 100}cqw`, height: `${b.radius * 100 * 0.4}cqw`,
                           transform: `translate(-50%,-50%) rotate(${b.inclined ?? 0}deg)` }} />
          ))}

          {/* sun = the core */}
          <div className="solsys-sun" ref={sunRef}>
            <button className={`solsys-body solsys-body--sun ${selected?.id === "sol" ? "is-selected" : ""}`} onClick={pick({ ...BODIES[0], ...SUN, id: "sol", tex: "", size: 0, radius: 0, speed: 0, phase: 0 } as Body)}
                    aria-label="ASTRAEA core runtime">
              <span className="solsys-sun-core" />
            </button>
            <span className="solsys-label">ASTRAEA</span>
          </div>

          {/* planets & dwarf */}
          {BODIES.map((b) => (
            <div key={b.id} className="solsys-body-wrap" ref={(n) => { bodyRefs.current[b.id] = n; }}>
              <button
                className={`solsys-body ${hover === b.id ? "is-hover" : ""} ${selected?.id === b.id ? "is-selected" : ""}`}
                style={{ width: b.size, height: b.size }}
                onClick={pick(b)}
                onPointerEnter={() => setHover(b.id)}
                onPointerLeave={() => setHover(null)}
                aria-label={`${b.module} — ${b.title}`}
              >
                <span className="solsys-globe">
                  <img className="solsys-tex" src={b.tex} alt="" draggable={false} />
                  <span className="solsys-shade" />
                  <span className="solsys-spec" />
                </span>
                {b.ring && <span className="solsys-planet-ring" />}
                {b.moons?.map((m, i) => (
                  <span key={m.name} className="solsys-moon-orbit"
                        style={{ width: b.size * m.dist * 2, height: b.size * m.dist * 2 * 0.45,
                                 animationDuration: `${8 / m.speed}s`, animationDelay: `${i * -2.5}s` }}>
                    <span className="solsys-moon" style={{ width: m.size, height: m.size }} title={m.name}>
                      <img src={m.tex} alt="" draggable={false} />
                    </span>
                  </span>
                ))}
              </button>
              <span className={`solsys-label ${hover === b.id || card?.id === b.id ? "show" : ""}`}>{b.module}</span>
            </div>
          ))}
        </div>
      </div>

      {/* ── feature card ── */}
      {mounted && card && createPortal(
        <aside className="solsys-card" role="dialog" aria-label={`${card.module} details`}>
          <button className="solsys-card-x" onClick={() => setSelected(null)} aria-label="close">✕</button>
          <p className="label label--accent">{card.name.toUpperCase()} · {card.module}</p>
          <h3 className="display" style={{ margin: "6px 0 2px", fontSize: 20 }}>{card.title}</h3>
          <p style={{ margin: "0 0 10px", fontSize: 13, color: "var(--ink-70)", lineHeight: 1.6 }}>{card.blurb}</p>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 10 }}>
            {card.features.map((f) => <span key={f} className="stamp stamp--shared">{f}</span>)}
          </div>
          {card.moons && card.moons.length > 0 && (
            <div className="solsys-moons">
              <p className="label label--ink">MOONS</p>
              {card.moons.map((m) => (
                <div key={m.name} className="solsys-moon-row">
                  <span className="solsys-moon-dot"><img src={m.tex} alt="" /></span>
                  <b>{m.name}</b>
                  <span>{m.note}</span>
                </div>
              ))}
            </div>
          )}
          <p className="label" style={{ margin: "0 0 10px" }}>◈ {card.benchmark}</p>
          <div style={{ display: "flex", gap: 8 }}>
            <Link href={card.href} className="btn btn--accent" style={{ fontSize: 12 }}>Open workbench →</Link>
            <Link href={card.docs} className="btn btn--ghost" style={{ fontSize: 12 }}>How it works</Link>
          </div>
        </aside>,
        document.body
      )}

      {mounted && createPortal(
        <p className="solsys-hint label">click any planet to explore the module · esc to close</p>,
        document.body
      )}
    </>
  );
}
