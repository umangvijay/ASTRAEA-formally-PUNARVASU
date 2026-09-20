"use client";

/**
 * ASTRAEA — NASA 3D Solar System & Planetary Feature Console.
 *
 * Ported from the approved Stitch reference: real-textured planets orbiting a
 * corona sun inside a 9,500-particle spiral galaxy, comets with ion/dust tails,
 * cinematic click-to-zoom camera kinematics, warp controls and an editorial
 * inspection drawer — with every planet mapped to a real ASTRAEA module.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import * as THREE from "three";

declare global {
  interface Window {
    selectPlanet?: (id: string) => void;
    resetCosmicView?: () => void;
    setSimulationSpeed?: (speed: number) => void;
    __animErr?: string;
  }
}

/* ── module registry: every planet IS a real ASTRAEA module ── */
type MoonSpec = { name: string; note: string; dist: number; size: number; speed: number };
type PlanetSpec = {
  id: string;
  name: string;
  module: string;
  title: string;
  category: string;
  description: string;
  specs: string;
  features: string[];
  workbench: string;
  docs: string;
  au: string;
  velocity: string;
  day: string;
  tilt: string;
  distance: number;
  radius: number;
  speed: number;
  type: string;
  tex: string | null;
  tint?: string;
  atmo?: string;
  tiltZ?: number;
  fusion?: boolean;
  ringType?: "saturn" | "jupiter";
  moons: MoonSpec[];
};

export const PLANETS: PlanetSpec[] = [
  {
    id: "mercury", name: "Mercury", module: "PULSE", title: "Real-time Telemetry Bus",
    category: "Core Telemetry Engine",
    description: "The stream everything shares: logs, metrics, deploys and security events from every service, ingested live and fed to MEDIC and SHIELD alike.",
    specs: "Detector heartbeat: 10 s · Ingest: X-Internal-Token pipeline · Store: SQLite ⇄ ClickHouse",
    features: ["Live metrics ingest", "Log & deploy events", "ClickHouse ⇄ SQLite", "Isolation-Forest feed"],
    workbench: "/console/medic", docs: "/docs/medic",
    au: "0.39 AU", velocity: "47.4 km/s", day: "1,408 hrs", tilt: "0.03°",
    distance: 35, radius: 2.4, speed: 0.007, type: "mercury", tex: "/cosmos/tex/2k_mercury.jpg", atmo: "#8a8f9c", tiltZ: 0.03,
    moons: [{ name: "Hermes Probe", note: "demo-services emitter", dist: 4.2, size: 0.45, speed: 0.02 }],
  },
  {
    id: "venus", name: "Venus", module: "VAULT", title: "Cryptographic Secrets Vault",
    category: "Zero-Trust Data Protection",
    description: "AES-256-GCM encryption at rest for every credential. Reveals are deliberate, audited actions; Argon2id passwords and login lockout guard the gate.",
    specs: "Cipher: AES-256-GCM · Hash: Argon2id · Lockout: 5 fails → 15 min · Audit: full trail",
    features: ["AES-256-GCM at rest", "Audited reveals", "Argon2id hashing", "Tenant API keys"],
    workbench: "/console/settings", docs: "/docs/settings",
    au: "0.72 AU", velocity: "35.0 km/s", day: "5,832 hrs", tilt: "177.4°",
    distance: 51, radius: 3.6, speed: 0.0052, type: "venus", tex: "/cosmos/tex/2k_venus.jpg", atmo: "#e8c98a", tiltZ: 3.09,
    moons: [{ name: "Kyber Key", note: "derived vault master key", dist: 5.6, size: 0.5, speed: 0.018 }],
  },
  {
    id: "earth", name: "Earth", module: "RUNS", title: "The Durable Run Engine",
    category: "Crash-proof Job Runtime",
    description: "The living world where jobs actually happen. Every step is an event, every run survives kill -9, and nothing risky happens without your approval.",
    specs: "Event-sourced · Gates: approval-required · Recovery: startup sweep · Watchdog: 30 s",
    features: ["Event-sourced steps", "Approval gates", "Crash recovery", "Full replay", "LLM streaming"],
    workbench: "/console/runs", docs: "/docs/runs",
    au: "1.00 AU", velocity: "29.8 km/s", day: "24 hrs", tilt: "23.4°",
    distance: 72, radius: 4.6, speed: 0.004, type: "earth", tex: "/cosmos/tex/2k_earth.jpg", atmo: "#5b8fe8", tiltZ: 0.41,
    moons: [{ name: "Luna", note: "MODEL-FORGE — our own model", dist: 8.2, size: 1.1, speed: 0.015 }],
  },
  {
    id: "mars", name: "Mars", module: "MEDIC", title: "The AI SRE — On-call Engineer",
    category: "Detect · Investigate · Fix",
    description: "Watches live telemetry with an Isolation Forest, ranks root causes, reproduces the fault against the service, and prepares the fix diff — approval before anything is applied.",
    specs: "MTTD: 8.9 s · Top-3 accuracy: 100% · Detection: 80% (5-fault bench) · Gate: human",
    features: ["Isolation-Forest detection", "Root-cause ranking", "Sandbox reproduction", "Fix diffs + PRs"],
    workbench: "/console/medic", docs: "/docs/medic",
    au: "1.52 AU", velocity: "24.1 km/s", day: "24.7 hrs", tilt: "25.2°",
    distance: 94, radius: 3.3, speed: 0.0031, type: "mars", tex: "/cosmos/tex/2k_mars.jpg", atmo: "#e0784a", tiltZ: 0.44,
    moons: [
      { name: "Phobos", note: "reproduce step", dist: 5.2, size: 0.5, speed: 0.022 },
      { name: "Deimos", note: "patch step", dist: 7.4, size: 0.4, speed: 0.014 },
    ],
  },
  {
    id: "jupiter", name: "Jupiter", module: "SHIELD", title: "The AI SOC Analyst",
    category: "Defensive Cyber Agent",
    description: "Correlates raw security events into incidents, maps them to MITRE ATT&CK, builds the attack graph and drafts containment — four detection families orbit it like moons.",
    specs: "Detection: 5/5 scenarios · Mapping: 100% · FP drill: 0.0% · Gate: human",
    features: ["Brute-force detection", "Port-scan detection", "Exfil & C2 beaconing", "Attack graphs", "Containment gate"],
    workbench: "/console/shield", docs: "/docs/shield",
    au: "5.20 AU", velocity: "13.1 km/s", day: "9.9 hrs", tilt: "3.1°",
    distance: 130, radius: 9.2, speed: 0.0018, type: "jupiter", tex: "/cosmos/tex/2k_jupiter.jpg", tint: "#b99a6e", atmo: "#d8b088", tiltZ: 0.05,
    ringType: "jupiter",
    moons: [
      { name: "Io · T1110", note: "brute force", dist: 13.2, size: 0.85, speed: 0.016 },
      { name: "Europa · T1046", note: "port scan", dist: 16.0, size: 0.8, speed: 0.013 },
      { name: "Ganymede · T1041", note: "exfiltration", dist: 19.0, size: 1.18, speed: 0.009 },
      { name: "Callisto · T1059", note: "malicious process", dist: 22.4, size: 1.0, speed: 0.007 },
    ],
  },
  {
    id: "saturn", name: "Saturn", module: "LOOM", title: "The Shared Memory",
    category: "Vector Memory & Provenance",
    description: "The ringed keeper of everything learned: every incident, fix and booking, embedded into a Chroma vector store with provenance stamps — searchable in plain English by every agent.",
    specs: "Embeddings: MiniLM 384-d · Store: ChromaDB · Recall: semantic, cross-module",
    features: ["Semantic search", "Provenance stamps", "Sharing matrix", "RAG for agents"],
    workbench: "/console/loom", docs: "/docs/memory",
    au: "9.58 AU", velocity: "9.7 km/s", day: "10.7 hrs", tilt: "26.7°",
    distance: 172, radius: 8.0, speed: 0.0012, type: "saturn", tex: "/cosmos/tex/2k_saturn.jpg", tint: "#c2ab7e", atmo: "#e0cfa0", tiltZ: 0.47,
    ringType: "saturn",
    moons: [
      { name: "Titan · Vector Search", note: "MiniLM embeddings", dist: 17.4, size: 1.15, speed: 0.011 },
      { name: "Enceladus · Provenance", note: "FROM/USED-BY stamps", dist: 20.8, size: 0.7, speed: 0.008 },
    ],
  },
  {
    id: "uranus", name: "Uranus", module: "FORGE", title: "The Self-Improvement Loop",
    category: "Nightly Consolidator",
    description: "Tipped on its side, marching to its own rules: mines real run failures nightly, proposes improvements, and promotes a candidate only when it measurably beats the champion — every promotion a git commit.",
    specs: "Eval: verifiable SQL · Champion: 73.3% · Promotion: only if strictly better",
    features: ["Failure mining", "Verifiable SQL evals", "Champion promotion", "Git-committed champions"],
    workbench: "/console/forge", docs: "/docs/forge",
    au: "19.2 AU", velocity: "6.8 km/s", day: "17.2 hrs", tilt: "97.8°",
    distance: 214, radius: 6.2, speed: 0.0009, type: "uranus", tex: "/cosmos/tex/2k_uranus.jpg", tint: "#58a8b5", atmo: "#9fd8de", tiltZ: 1.71,
    moons: [
      { name: "Titania · Consolidator", note: "nightly miner", dist: 9.6, size: 0.9, speed: 0.012 },
      { name: "Oberon · Eval Suite", note: "held-out SQL tasks", dist: 12.2, size: 0.75, speed: 0.009 },
    ],
  },
  {
    id: "neptune", name: "Neptune", module: "VAANI", title: "The Voice AI Employee",
    category: "Full-duplex Voice Agent",
    description: "The far blue world answers the phone: Silero VAD, faster-whisper STT, a brain with your Memory context, and bookings that become durable runs. Talk over it — barge-in cancels mid-sentence.",
    specs: "STT: 1,243 ms · Brain: 2,422 ms · Bookings: durable runs · Barge-in: live",
    features: ["Silero VAD", "faster-whisper STT", "Memory-context brain", "Sentence-level TTS"],
    workbench: "/console/vaani", docs: "/docs/vaani",
    au: "30.1 AU", velocity: "5.4 km/s", day: "16.1 hrs", tilt: "28.3°",
    distance: 254, radius: 5.9, speed: 0.0007, type: "neptune", tex: "/cosmos/tex/2k_neptune.jpg", tint: "#4f6fc0", atmo: "#5b7bd5", tiltZ: 0.49,
    moons: [{ name: "Triton · Barge-in", note: "TTS cancel < 100 ms", dist: 9.8, size: 0.95, speed: 0.014 }],
  },
];

const SUN_SPEC: PlanetSpec = {
  id: "sol", name: "Sol", module: "ASTRAEA", title: "Fusion — All Modules",
  category: "The Core Runtime · every module, one workspace",
  description: "The returning light at the center. FUSION runs every module together on one durable engine — shared vector memory, cross-module workflows, one live timeline. Click any module below to open its workbench.",
  specs: "Runs: event-sourced, survive kill -9 · Gates: human approval · Replay: from any event",
  features: ["Event-sourced runs", "Approval gates", "Crash recovery", "Watchdog self-heal", "Shared vector memory"],
  workbench: "/console/fusion", docs: "/docs/runs",
  au: "CENTER", velocity: "—", day: "—", tilt: "—",
  distance: 0, radius: 15, speed: 0, type: "sun", tex: null, fusion: true,
  moons: [],
};

/* ── procedural fallback textures (used if a real texture fails to load) ── */
function proceduralTexture(type: string): THREE.Texture {
  const canvas = document.createElement("canvas");
  canvas.width = 1024;
  canvas.height = 512;
  const ctx = canvas.getContext("2d")!;
  const palettes: Record<string, [string, string, string]> = {
    mercury: ["#7a7d84", "#4c5058", "#2b2e35"],
    venus: ["#eedbb5", "#c99f5a", "#a87834"],
    earth: ["#0a2e5c", "#1d5e38", "#9e7631"],
    mars: ["#c8562d", "#b24120", "#3e1b0c"],
    jupiter: ["#ecd9b5", "#b97441", "#8d4722"],
    saturn: ["#e0c99f", "#cbaf80", "#6e502b"],
    uranus: ["#9fd8dc", "#6fb9c4", "#4a93a3"],
    neptune: ["#3b5bdc", "#2f4ab8", "#1e2f7d"],
    moon: ["#d6d3d1", "#a8a5a2", "#57544f"],
  };
  const [base, mid, dark] = palettes[type] ?? ["#8a8f9c", "#5a5f6c", "#2b2e35"];
  ctx.fillStyle = base;
  ctx.fillRect(0, 0, 1024, 512);
  for (let i = 0; i < 90; i++) {
    ctx.globalAlpha = 0.18 + Math.random() * 0.3;
    ctx.fillStyle = Math.random() > 0.5 ? mid : dark;
    ctx.beginPath();
    ctx.ellipse(Math.random() * 1024, Math.random() * 512, Math.random() * 120 + 20, Math.random() * 46 + 8, Math.random() * Math.PI, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.globalAlpha = 1;
  const t = new THREE.CanvasTexture(canvas);
  t.wrapS = THREE.RepeatWrapping;
  return t;
}

function softDotTexture(rgb = "255,255,255"): THREE.Texture {
  const c = document.createElement("canvas");
  c.width = c.height = 64;
  const ctx = c.getContext("2d")!;
  const g = ctx.createRadialGradient(32, 32, 0, 32, 32, 32);
  g.addColorStop(0, `rgba(${rgb},1)`);
  g.addColorStop(0.35, `rgba(${rgb},0.5)`);
  g.addColorStop(1, `rgba(${rgb},0)`);
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, 64, 64);
  return new THREE.CanvasTexture(c);
}

/** Load a real galaxy photograph (NASA/ESA public-domain imagery) and fade its
 *  edges into space with a radial mask so the sprite blends into the sky. */
function maskedGalaxyTexture(url: string, cb: (t: THREE.CanvasTexture) => void) {
  const img = new Image();
  img.onload = () => {
    const size = 512;
    const c = document.createElement("canvas");
    c.width = c.height = size;
    const ctx = c.getContext("2d")!;
    const s = Math.max(size / img.width, size / img.height);
    const w = img.width * s, h = img.height * s;
    ctx.drawImage(img, (size - w) / 2, (size - h) / 2, w, h);
    const g = ctx.createRadialGradient(size / 2, size / 2, size * 0.16, size / 2, size / 2, size * 0.5);
    g.addColorStop(0, "rgba(0,0,0,1)");
    g.addColorStop(0.72, "rgba(0,0,0,0.82)");
    g.addColorStop(1, "rgba(0,0,0,0)");
    ctx.globalCompositeOperation = "destination-in";
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, size, size);
    const t = new THREE.CanvasTexture(c);
    t.colorSpace = THREE.SRGBColorSpace;
    cb(t);
  };
  img.src = url;
}

function saturnRingTexture(): THREE.Texture {  const canvas = document.createElement("canvas");
  canvas.width = 1024;
  canvas.height = 64;
  const ctx = canvas.getContext("2d")!;
  const grad = ctx.createLinearGradient(0, 0, 1024, 0);
  grad.addColorStop(0.0, "rgba(0,0,0,0)");
  grad.addColorStop(0.08, "rgba(150,130,105,0.18)");
  grad.addColorStop(0.25, "rgba(215,195,160,0.78)");
  grad.addColorStop(0.55, "rgba(240,222,185,0.96)");
  grad.addColorStop(0.58, "rgba(8,6,4,0.04)");
  grad.addColorStop(0.62, "rgba(205,185,150,0.88)");
  grad.addColorStop(0.84, "rgba(185,165,135,0.68)");
  grad.addColorStop(0.92, "rgba(145,125,100,0.35)");
  grad.addColorStop(1.0, "rgba(0,0,0,0)");
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, 1024, 64);
  for (let r = 80; r < 950; r += 5) {
    if (r >= 560 && r <= 620) continue;
    ctx.fillStyle = Math.random() > 0.5 ? "rgba(0,0,0,0.18)" : "rgba(255,255,255,0.16)";
    ctx.fillRect(r, 0, 2, 64);
  }
  return new THREE.CanvasTexture(canvas);
}

function jupiterRingTexture(): THREE.Texture {
  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = 32;
  const ctx = canvas.getContext("2d")!;
  const grad = ctx.createLinearGradient(0, 0, 512, 0);
  grad.addColorStop(0.0, "rgba(0,0,0,0)");
  grad.addColorStop(0.35, "rgba(195,145,95,0.12)");
  grad.addColorStop(0.7, "rgba(230,175,120,0.32)");
  grad.addColorStop(0.9, "rgba(185,130,80,0.14)");
  grad.addColorStop(1.0, "rgba(0,0,0,0)");
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, 512, 32);
  return new THREE.CanvasTexture(canvas);
}

const loader = new THREE.TextureLoader();
function planetTexture(type: string, file: string | null): THREE.Texture {
  if (file) {
    const t = loader.load(file, undefined, undefined, () => {
      // on error swap in the procedural fallback
      t.image = proceduralTexture(type).image;
      t.needsUpdate = true;
    });
    t.wrapS = THREE.RepeatWrapping;
    t.colorSpace = THREE.SRGBColorSpace;
    return t;
  }
  return proceduralTexture(type);
}

export function SolarSystem3D() {
  const mountRef = useRef<HTMLDivElement>(null);
  const [selected, setSelected] = useState<PlanetSpec | null>(null);
  const [heroHidden, setHeroHidden] = useState(false);
  const [warp, setWarp] = useState(1);
  const [mounted, setMounted] = useState(false);
  useEffect(() => { setMounted(true); }, []);

  const selectRef = useRef<(id: string) => void>(() => {});
  const resetRef = useRef<() => void>(() => {});
  const warpRef = useRef<(s: number) => void>(() => {});

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;

    const width = mount.clientWidth || window.innerWidth;
    const height = mount.clientHeight || window.innerHeight;

    const scene = new THREE.Scene();
    scene.fog = new THREE.FogExp2(0x000000, 0.0004);

    const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 5000);
    camera.position.set(0, 95, 230);
    const camFill = new THREE.PointLight(0xdfe8ff, 0.55, 0, 0); // gentle inspection fill, rides with camera
    camera.add(camFill);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "high-performance" });
    renderer.setSize(width, height);
    // adaptive DPR: small screens get 1.5 (fewer pixels → smoother), desktop 1.75
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, width < 900 ? 1.5 : 1.75));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.0;
    mount.appendChild(renderer.domElement);

    const ambient = new THREE.AmbientLight(0x3c3c42, 1.35);
    scene.add(ambient);
    // three r155+ physical lights: decay 0 keeps orbit-distance planets lit
    const sunLight = new THREE.PointLight(0xfffae8, 1.25, 0, 0);
    const fillLight = new THREE.PointLight(0xb8c0d0, 0.25, 0, 0); // neutral cool fill so night sides read
    fillLight.position.set(-180, 120, -160);
    scene.add(sunLight);
    scene.add(fillLight);

    /* the whole solar system — it precesses and drifts through the galaxy */
    const systemGroup = new THREE.Group();
    scene.add(systemGroup);
    const sunAnchor = new THREE.Group();
    systemGroup.add(sunAnchor);

    /* ── Milky Way: 9,500-particle 5-arm spiral ── */
    const galaxyGroup = new THREE.Group();
    let galaxyMat: THREE.PointsMaterial;
    {
      const count = 13000;
      const geo = new THREE.BufferGeometry();
      const pos = new Float32Array(count * 3);
      const col = new Float32Array(count * 3);
      const cCore = new THREE.Color(0xe6daf5);
      const cArm = new THREE.Color(0x9db8cc);
      const cDust = new THREE.Color(0xe8a063);
      for (let i = 0; i < count; i++) {
        const i3 = i * 3;
        const radius = Math.random() * 950 + 40;
        const spin = radius * 0.0045;
        const branch = ((i % 5) * (Math.PI * 2)) / 5;
        const rx = Math.pow(Math.random(), 3) * (Math.random() < 0.5 ? 1 : -1) * 36;
        const ry = Math.pow(Math.random(), 3) * (Math.random() < 0.5 ? 1 : -1) * 30;
        const rz = Math.pow(Math.random(), 3) * (Math.random() < 0.5 ? 1 : -1) * 36;
        pos[i3] = Math.cos(branch + spin) * radius + rx;
        pos[i3 + 1] = ry * (1.2 - radius / 950);
        pos[i3 + 2] = Math.sin(branch + spin) * radius + rz;
        const c = cCore.clone().lerp(cArm, radius / 950);
        if (Math.random() > 0.8) c.lerp(cDust, 0.65);
        col[i3] = c.r; col[i3 + 1] = c.g; col[i3 + 2] = c.b;
      }
      geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
      geo.setAttribute("color", new THREE.BufferAttribute(col, 3));
      galaxyMat = new THREE.PointsMaterial({ size: 2.7, map: softDotTexture("255,255,255"), vertexColors: true, transparent: true, opacity: 0.85, blending: THREE.AdditiveBlending, depthWrite: false });
      const points = new THREE.Points(geo, galaxyMat);
      galaxyGroup.add(points);
      // glowing galactic core
      const core = new THREE.Sprite(new THREE.SpriteMaterial({ map: softDotTexture("230,218,245"), color: 0xe6daf5, transparent: true, opacity: 0.7, blending: THREE.AdditiveBlending, depthWrite: false }));
      core.scale.setScalar(210);
      galaxyGroup.add(core);
      galaxyGroup.position.set(0, -45, -190);
      galaxyGroup.rotation.x = 0.38;
      galaxyGroup.rotation.z = -0.15;
      scene.add(galaxyGroup);
    }

    /* ── more deep-sky galaxies ──
       A second spiral (golden, tilted the other way), an elliptical, and
       distant fuzzy companions — grouped so the whole deep field drifts. */
    const farGalaxyMats: THREE.Material[] = [];
    const farGalaxies = new THREE.Group();
    {
      const count = 7000;
      const geo = new THREE.BufferGeometry();
      const pos = new Float32Array(count * 3);
      const col = new Float32Array(count * 3);
      const cCore = new THREE.Color(0xffe4c0);
      const cArm = new THREE.Color(0xf0a884);
      const cDust = new THREE.Color(0xd4789c);
      for (let i = 0; i < count; i++) {
        const i3 = i * 3;
        const radius = Math.random() * 620 + 30;
        const spin = radius * 0.006;
        const branch = ((i % 4) * (Math.PI * 2)) / 4;
        const spread = Math.pow(Math.random(), 3) * (Math.random() < 0.5 ? 1 : -1);
        pos[i3] = Math.cos(branch + spin) * radius + spread * 22;
        pos[i3 + 1] = spread * 18 * (1.2 - radius / 620);
        pos[i3 + 2] = Math.sin(branch + spin) * radius + spread * 22;
        const c = cCore.clone().lerp(cArm, radius / 620);
        if (Math.random() > 0.82) c.lerp(cDust, 0.6);
        col[i3] = c.r; col[i3 + 1] = c.g; col[i3 + 2] = c.b;
      }
      geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
      geo.setAttribute("color", new THREE.BufferAttribute(col, 3));
      const g2Mat = new THREE.PointsMaterial({ size: 2.2, map: softDotTexture("255,255,255"), vertexColors: true, transparent: true, opacity: 0.78, blending: THREE.AdditiveBlending, depthWrite: false });
      g2Mat.userData.baseOpacity = 0.78;
      farGalaxyMats.push(g2Mat);
      const g2 = new THREE.Group();
      g2.add(new THREE.Points(geo, g2Mat));
      const core2 = new THREE.Sprite(new THREE.SpriteMaterial({ map: softDotTexture("255,228,192"), color: 0xffe4c0, transparent: true, opacity: 0.7, blending: THREE.AdditiveBlending, depthWrite: false }));
      core2.scale.setScalar(120);
      g2.add(core2);
      g2.position.set(280, 130, -620);
      g2.rotation.set(1.15, 0.5, -0.45);
      farGalaxies.add(g2);
    }
    {
      // elliptical: dense warm core with a gaussian halo
      const count = 3600;
      const geo = new THREE.BufferGeometry();
      const pos = new Float32Array(count * 3);
      const col = new Float32Array(count * 3);
      const cIn = new THREE.Color(0xfff2d8);
      const cOut = new THREE.Color(0xd9c8a8);
      const gauss = () => (Math.random() + Math.random() + Math.random() - 1.5) / 1.5;
      for (let i = 0; i < count; i++) {
        const i3 = i * 3;
        pos[i3] = gauss() * 150;
        pos[i3 + 1] = gauss() * 54;
        pos[i3 + 2] = gauss() * 150;
        const c = cIn.clone().lerp(cOut, Math.min(1, Math.hypot(pos[i3], pos[i3 + 2]) / 150));
        col[i3] = c.r; col[i3 + 1] = c.g; col[i3 + 2] = c.b;
      }
      geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
      geo.setAttribute("color", new THREE.BufferAttribute(col, 3));
      const eMat = new THREE.PointsMaterial({ size: 2.0, map: softDotTexture("255,255,255"), vertexColors: true, transparent: true, opacity: 0.6, blending: THREE.AdditiveBlending, depthWrite: false });
      eMat.userData.baseOpacity = 0.6;
      farGalaxyMats.push(eMat);
      const eg = new THREE.Group();
      eg.add(new THREE.Points(geo, eMat));
      const eCore = new THREE.Sprite(new THREE.SpriteMaterial({ map: softDotTexture("255,242,216"), color: 0xfff2d8, transparent: true, opacity: 0.55, blending: THREE.AdditiveBlending, depthWrite: false }));
      eCore.scale.setScalar(90);
      eg.add(eCore);
      eg.position.set(-320, -90, -700);
      eg.rotation.set(0.2, 0.8, 0.35);
      farGalaxies.add(eg);
    }
    // distant companions — small fuzzy glows across the deep field
    const companions: [number, number, number, number, string][] = [
      [200, 180, -820, 70, "216,180,254"],
      [-260, -160, -760, 52, "150,220,232"],
      [60, 250, -900, 84, "255,200,160"],
      [-140, -240, -640, 46, "180,200,255"],
      [310, -50, -880, 58, "255,180,190"],
    ];
    for (const [x, y, z, scale, tint] of companions) {
      const m = new THREE.SpriteMaterial({ map: softDotTexture(tint), color: 0xffffff, transparent: true, opacity: 0.32, blending: THREE.AdditiveBlending, depthWrite: false });
      m.userData.baseOpacity = 0.32;
      farGalaxyMats.push(m);
      const s = new THREE.Sprite(m);
      s.position.set(x, y, z);
      s.scale.setScalar(scale);
      farGalaxies.add(s);
    }
    // the real deep sky — NASA/ESA photographs (public domain), masked into
    // soft-edged billboards framing the solar system
    const realGalaxies: { file: string; pos: [number, number, number]; scale: number; opacity: number }[] = [
      { file: "/cosmos/galaxies/andromeda.jpg", pos: [-260, 150, -640], scale: 260, opacity: 0.6 },
      { file: "/cosmos/galaxies/whirlpool.jpg", pos: [300, -20, -620], scale: 220, opacity: 0.58 },
      { file: "/cosmos/galaxies/sombrero.jpg", pos: [-240, -160, -560], scale: 200, opacity: 0.55 },
      { file: "/cosmos/galaxies/cartwheel.jpg", pos: [200, 190, -700], scale: 190, opacity: 0.5 },
    ];
    for (const g of realGalaxies) {
      const mat = new THREE.SpriteMaterial({
        map: softDotTexture("180,190,255"),
        color: 0xffffff, transparent: true, opacity: g.opacity,
        blending: THREE.AdditiveBlending, depthWrite: false,
      });
      mat.userData.baseOpacity = g.opacity;
      farGalaxyMats.push(mat);
      const spr = new THREE.Sprite(mat);
      spr.position.set(...g.pos);
      spr.scale.setScalar(g.scale);
      farGalaxies.add(spr);
      maskedGalaxyTexture(g.file, (tex) => {
        mat.map = tex;
        mat.needsUpdate = true;
      });
    }
    scene.add(farGalaxies);

    /* ── the real night sky ────────────────────────────────────────────
       Naked-eye stars at their actual celestial coordinates (RA hours,
       Dec degrees, visual magnitude, approximate blackbody color), placed on
       the celestial sphere — plus a procedural faint fill weighted toward
       the galactic band. Pixel-consistent sizes (sizeAttenuation off) so a
       star is a star at any camera distance, never a near-camera square. */
    const starTex = softDotTexture();
    const REAL_STARS: [number, number, number, number][] = [
      // [RA hours, Dec degrees, apparent magnitude, color]
      [6.75, -16.7, -1.46, 0xeaf1ff],   // Sirius
      [6.4, -52.7, -0.74, 0xfff4e0],    // Canopus
      [14.66, -60.8, -0.27, 0xfff6e8],  // Rigil Kentaurus
      [14.26, 19.2, -0.05, 0xffd9a0],   // Arcturus
      [18.62, 38.8, 0.03, 0xeef4ff],    // Vega
      [5.28, 46.0, 0.08, 0xfff3c8],     // Capella
      [5.24, -8.2, 0.13, 0xdde8ff],     // Rigel
      [7.65, 5.2, 0.34, 0xfff8ea],      // Procyon
      [5.92, 7.4, 0.42, 0xffb46b],      // Betelgeuse
      [1.63, -57.2, 0.46, 0xcfe0ff],    // Achernar
      [14.06, -60.4, 0.61, 0xcfe0ff],   // Hadar
      [19.85, 8.9, 0.76, 0xf4f8ff],     // Altair
      [12.44, -63.1, 0.76, 0xcfe0ff],   // Acrux
      [4.6, 16.5, 0.86, 0xffc389],      // Aldebaran
      [16.49, -26.4, 1.06, 0xff9e66],   // Antares
      [13.42, -11.2, 0.97, 0xcfe0ff],   // Spica
      [7.76, 28.0, 1.14, 0xffd9a8],     // Pollux
      [22.96, -29.6, 1.16, 0xf4f8ff],   // Fomalhaut
      [20.69, 45.3, 1.25, 0xf4f8ff],    // Deneb
      [12.79, -59.7, 1.25, 0xcfe0ff],   // Mimosa
      [10.14, 12.0, 1.39, 0xe8f0ff],    // Regulus
      [6.98, -29.0, 1.5, 0xcfe0ff],     // Adhara
      [7.58, 31.9, 1.58, 0xf4f8ff],     // Castor
      [17.56, -37.1, 1.62, 0xcfe0ff],   // Shaula
      [12.52, -57.1, 1.64, 0xffb37a],   // Gacrux
      [5.42, 6.3, 1.64, 0xcfe0ff],      // Bellatrix
      [5.44, 28.6, 1.65, 0xf4f8ff],     // Elnath
      [9.22, -69.7, 1.68, 0xf4f8ff],    // Miaplacidus
      [5.6, -1.2, 1.69, 0xcfe0ff],      // Alnilam
      [22.14, -46.9, 1.74, 0xcfe0ff],   // Alnair
      [5.68, -1.9, 1.77, 0xcfe0ff],     // Alnitak
      [12.9, 56.0, 1.77, 0xf4f8ff],     // Alioth
      [11.06, 61.8, 1.79, 0xffe9b8],    // Dubhe
      [3.4, 49.9, 1.8, 0xf4f8ff],       // Mirfak
      [7.14, -26.4, 1.83, 0xfff0c8],    // Wezen
      [8.16, -47.3, 1.83, 0xcfe0ff],    // Regor
      [18.4, -34.4, 1.85, 0xcfe0ff],    // Kaus Australis
      [8.38, -59.5, 1.86, 0xffd9a8],    // Avior
      [13.79, 49.3, 1.86, 0xcfe0ff],    // Alkaid
      [5.99, 44.9, 1.9, 0xf4f8ff],      // Menkalinan
      [16.81, -69.0, 1.91, 0xffb46b],   // Atria
      [6.63, 16.4, 1.92, 0xf4f8ff],     // Alhena
      [20.43, -56.7, 1.94, 0xcfe0ff],   // Peacock
      [2.53, 89.3, 1.98, 0xf4f8ff],     // Polaris
      [6.38, -18.0, 1.98, 0xcfe0ff],    // Mirzam
      [9.46, -8.7, 1.99, 0xffb46b],     // Alphard
      [2.12, 23.5, 2.0, 0xffd9a8],      // Hamal
      [0.44, -18.0, 2.04, 0xffb46b],    // Diphda
      [13.4, 54.9, 2.04, 0xf4f8ff],     // Mizar
      [18.92, -26.3, 2.06, 0xcfe0ff],   // Nunki
      [14.11, -36.4, 2.06, 0xffb46b],   // Menkent
      [1.16, 35.6, 2.05, 0xffb46b],     // Mirach
      [0.14, 29.1, 2.06, 0xf4f8ff],     // Alpheratz
      [17.58, 12.6, 2.08, 0xf4f8ff],    // Rasalhague
      [14.84, 74.2, 2.08, 0xffc389],    // Kochab
      [5.8, -9.7, 2.09, 0xcfe0ff],      // Saiph
      [11.82, 14.6, 2.14, 0xf4f8ff],    // Denebola
      [3.14, 41.0, 2.12, 0xf4f8ff],     // Algol
      [22.71, -46.9, 2.1, 0xffb46b],    // Tiaki
      [10.33, 19.8, 2.08, 0xffc389],    // Algieba
      [12.69, -48.9, 2.2, 0xf4f8ff],    // Muhlifain
      [9.28, -59.3, 2.25, 0xfff0c8],    // Aspidiske
      [9.13, -43.4, 2.23, 0xffb46b],    // Suhail
      [15.58, 26.7, 2.23, 0xf4f8ff],    // Alphecca
      [5.53, -0.3, 2.23, 0xcfe0ff],     // Mintaka
      [20.37, 40.3, 2.23, 0xfff0c8],    // Sadr
      [17.94, 51.5, 2.23, 0xffb46b],    // Eltanin
      [0.68, 56.5, 2.24, 0xffc389],     // Schedar
      [8.04, -40.0, 2.25, 0xcfe0ff],    // Naos
      [2.06, 42.3, 2.26, 0xffd9a8],     // Almach
      [0.15, 59.1, 2.28, 0xfff0c8],     // Caph
      [13.66, -53.5, 2.3, 0xcfe0ff],    // Epsilon Centauri
      [11.59, -63.0, 2.3, 0xcfe0ff],    // Lambda Centauri
      [14.75, 27.1, 2.37, 0xffb46b],    // Izar
      [11.03, 56.4, 2.37, 0xf4f8ff],    // Merak
      [21.74, 9.9, 2.39, 0xffb46b],     // Enif
      [0.44, -42.3, 2.38, 0xffb46b],    // Ankaa
      [23.08, 15.2, 2.49, 0xf4f8ff],    // Markab
      [23.06, 28.1, 2.42, 0xff9e66],    // Scheat
      [17.17, -15.7, 2.43, 0xf4f8ff],   // Sabik
      [11.9, 53.7, 2.44, 0xf4f8ff],     // Phecda
      [7.4, -29.3, 2.45, 0xcfe0ff],     // Aludra
      [21.31, 62.6, 2.45, 0xf4f8ff],    // Alderamin
      [11.24, 20.5, 2.56, 0xf4f8ff],    // Zosma
      [12.26, -17.5, 2.59, 0xffb46b],   // Gienah
      [1.43, 60.4, 2.68, 0xf4f8ff],     // Ruchbah
    ];
    const starGroup = new THREE.Group();
    const starMats: THREE.PointsMaterial[] = [];
    const skyRadius = 1400;
    const starSc = new THREE.Color();

    const buildStarLayer = (pts: [number, number, number, number][], sizePx: number, opacity: number) => {
      const geo = new THREE.BufferGeometry();
      const pos = new Float32Array(pts.length * 3);
      const col = new Float32Array(pts.length * 3);
      pts.forEach(([raH, decD, mag, hex], i) => {
        const ra = (raH / 24) * Math.PI * 2;
        const dec = (decD * Math.PI) / 180;
        pos[i * 3] = skyRadius * Math.cos(dec) * Math.cos(ra);
        pos[i * 3 + 1] = skyRadius * Math.sin(dec);
        pos[i * 3 + 2] = -skyRadius * Math.cos(dec) * Math.sin(ra);
        starSc.setHex(hex).multiplyScalar(0.7 + 0.3 * Math.max(0, Math.min(1, (2.8 - mag) / 3.4)));
        col[i * 3] = starSc.r; col[i * 3 + 1] = starSc.g; col[i * 3 + 2] = starSc.b;
      });
      geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
      geo.setAttribute("color", new THREE.BufferAttribute(col, 3));
      const mat = new THREE.PointsMaterial({
        size: sizePx, map: starTex, vertexColors: true, transparent: true,
        opacity, depthWrite: false, blending: THREE.AdditiveBlending,
        sizeAttenuation: false, // pixel-consistent — stars never balloon near the camera
      });
      starMats.push(mat);
      starGroup.add(new THREE.Points(geo, mat));
    };

    // bucket the real catalog by brightness (PointsMaterial has one size per layer)
    buildStarLayer(REAL_STARS.filter(s => s[2] < 1.2), 4.4, 1.0);
    buildStarLayer(REAL_STARS.filter(s => s[2] >= 1.2 && s[2] < 2.2), 3.1, 0.95);
    buildStarLayer(REAL_STARS.filter(s => s[2] >= 2.2), 2.2, 0.9);

    // faint procedural fill — extra density along the galactic band (the Milky Way)
    const fillPts: [number, number, number, number][] = [];
    for (let i = 0; i < 2400; i++) {
      const inBand = Math.random() < 0.45;
      const raH = Math.random() * 24;
      const decD = inBand
        ? (Math.random() - 0.5) * 46 + Math.sin((raH / 24) * Math.PI * 2) * 28 - 18
        : (Math.random() - 0.5) * 170;
      fillPts.push([raH, decD, 3.1 + Math.random() * 1.8, 0xf4f8ff]);
    }
    buildStarLayer(fillPts, 1.6, 0.8);
    scene.add(starGroup);

    /* ── theme-aware sky ──
       The space canvas keeps its blazing starfield in BOTH themes — only the
       UI glass (nav, cards) switches between Day and Night. Day runs the sky
       a touch dimmer so light panels still contrast against it. */
    const starBase: number[] = [];
    const applySkyTheme = () => {
      const day = document.documentElement.dataset.theme !== "dark";
      starMats.forEach((m, i) => { starBase[i] = i === starMats.length - 1 ? (day ? 0.7 : 0.8) : (day ? 0.8 : 0.92); });
      galaxyMat.opacity = day ? 0.72 : 0.85;
      farGalaxyMats.forEach((m) => { m.opacity = (m.userData.baseOpacity ?? 0.6) * (day ? 0.85 : 1); });
    };
    applySkyTheme();
    const themeObserver = new MutationObserver(applySkyTheme);
    themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    // debug handle (same pattern as __frames) — live sky state for checks
    (window as unknown as { __sky?: unknown }).__sky = { starMats, farGalaxyMats, galaxyMat, starBase };

    /* ── the sun + corona + flare ring ── */
    let sunMesh: THREE.Mesh, coronaMesh: THREE.Mesh, flareMesh: THREE.Mesh;
    {
      const realSun = loader.load("/cosmos/tex/2k_sun.jpg", undefined, undefined, () => {
        const sunCanvas = document.createElement("canvas");
        sunCanvas.width = 512; sunCanvas.height = 256;
        const sctx = sunCanvas.getContext("2d")!;
        const sg = sctx.createLinearGradient(0, 0, 512, 0);
        sg.addColorStop(0, "#fef08a"); sg.addColorStop(0.5, "#f59e0b"); sg.addColorStop(1, "#ea580c");
        sctx.fillStyle = sg;
        sctx.fillRect(0, 0, 512, 256);
        for (let g = 0; g < 180; g++) {
          sctx.fillStyle = "#ffedd5";
          sctx.globalAlpha = 0.35;
          sctx.beginPath();
          sctx.arc(Math.random() * 512, Math.random() * 256, Math.random() * 12 + 4, 0, Math.PI * 2);
          sctx.fill();
        }
        realSun.image = new THREE.CanvasTexture(sunCanvas).image;
        realSun.needsUpdate = true;
      });
      realSun.colorSpace = THREE.SRGBColorSpace;
      sunMesh = new THREE.Mesh(new THREE.SphereGeometry(15, 48, 48), new THREE.MeshBasicMaterial({ map: realSun }));
      sunAnchor.add(sunMesh);
      coronaMesh = new THREE.Mesh(
        new THREE.SphereGeometry(17.5, 32, 32),
        new THREE.MeshBasicMaterial({ color: 0xf59e0b, transparent: true, opacity: 0.26, side: THREE.BackSide, blending: THREE.AdditiveBlending })
      );
      sunAnchor.add(coronaMesh);
      flareMesh = new THREE.Mesh(
        new THREE.RingGeometry(15.5, 23.5, 48),
        new THREE.MeshBasicMaterial({ color: 0xfb923c, side: THREE.DoubleSide, transparent: true, opacity: 0.42, blending: THREE.AdditiveBlending })
      );
      flareMesh.rotation.x = Math.PI / 2.15;
      sunAnchor.add(flareMesh);
    }

    /* ── planets, orbits, rings, moons ── */
    const interactive: THREE.Mesh[] = [];
    const moonPivots: { pivot: THREE.Group; speed: number }[] = [];

    for (const spec of PLANETS) {
      const orbitGeo = new THREE.BufferGeometry();
      const pts: number[] = [];
      for (let s = 0; s <= 160; s++) {
        const th = (s / 160) * Math.PI * 2;
        pts.push(Math.cos(th) * spec.distance, 0, Math.sin(th) * spec.distance);
      }
      orbitGeo.setAttribute("position", new THREE.Float32BufferAttribute(pts, 3));
      systemGroup.add(new THREE.Line(orbitGeo, new THREE.LineBasicMaterial({ color: 0x818cf8, transparent: true, opacity: 0.28 })));

      const pivot = new THREE.Group();
      systemGroup.add(pivot);

      const mesh = new THREE.Mesh(
        new THREE.SphereGeometry(spec.radius, 48, 48),
        new THREE.MeshStandardMaterial({ map: planetTexture(spec.type, spec.tex), color: spec.tint ?? "#ffffff", roughness: spec.type === "earth" ? 0.45 : 0.72, metalness: 0.08 })
      );
      // atmospheric limb: thin additive halo hugging the limb reads as real depth
      if (spec.atmo) {
        const atmo = new THREE.Mesh(
          new THREE.SphereGeometry(spec.radius * 1.045, 48, 48),
          new THREE.MeshBasicMaterial({ color: spec.atmo, transparent: true, opacity: 0.16, side: THREE.BackSide, blending: THREE.AdditiveBlending, depthWrite: false })
        );
        mesh.add(atmo);
      }
      if (spec.tiltZ) mesh.rotation.z = spec.tiltZ;
      mesh.position.x = spec.distance;
      pivot.add(mesh);

      if (spec.ringType === "saturn") {
        const ringGeo = new THREE.RingGeometry(spec.radius * 1.35, spec.radius * 2.55, 96);
        const p = ringGeo.attributes.position;
        const uv = ringGeo.attributes.uv;
        for (let i = 0; i < p.count; i++) {
          const d = Math.hypot(p.getX(i), p.getY(i));
          uv.setXY(i, (d - spec.radius * 1.35) / (spec.radius * 2.55 - spec.radius * 1.35), 0.5);
        }
        uv.needsUpdate = true;
        const ring = new THREE.Mesh(ringGeo, new THREE.MeshStandardMaterial({ map: saturnRingTexture(), side: THREE.DoubleSide, transparent: true, opacity: 0.94, roughness: 0.55 }));
        ring.rotation.x = Math.PI / 2.35;
        ring.rotation.y = 0.12;
        mesh.add(ring);
      } else if (spec.ringType === "jupiter") {
        const ringGeo = new THREE.RingGeometry(spec.radius * 1.15, spec.radius * 1.55, 64);
        const p = ringGeo.attributes.position;
        const uv = ringGeo.attributes.uv;
        for (let i = 0; i < p.count; i++) {
          const d = Math.hypot(p.getX(i), p.getY(i));
          uv.setXY(i, (d - spec.radius * 1.15) / (spec.radius * 1.55 - spec.radius * 1.15), 0.5);
        }
        uv.needsUpdate = true;
        const ring = new THREE.Mesh(ringGeo, new THREE.MeshBasicMaterial({ map: jupiterRingTexture(), side: THREE.DoubleSide, transparent: true, opacity: 0.38, blending: THREE.AdditiveBlending }));
        ring.rotation.x = Math.PI / 2.1;
        mesh.add(ring);
      }

      for (const m of spec.moons) {
        const moonPivot = new THREE.Group();
        mesh.add(moonPivot);
        const moon = new THREE.Mesh(
          new THREE.SphereGeometry(m.size, 24, 24),
          new THREE.MeshStandardMaterial({ map: planetTexture("moon", "/cosmos/tex/2k_moon.jpg"), roughness: 0.9 })
        );
        moon.position.x = m.dist;
        moonPivot.add(moon);
        const mGeo = new THREE.BufferGeometry();
        const mPts: number[] = [];
        for (let s = 0; s <= 48; s++) {
          const th = (s / 48) * Math.PI * 2;
          mPts.push(Math.cos(th) * m.dist, 0, Math.sin(th) * m.dist);
        }
        mGeo.setAttribute("position", new THREE.Float32BufferAttribute(mPts, 3));
        moonPivot.add(new THREE.Line(mGeo, new THREE.LineBasicMaterial({ color: 0x94a3b8, transparent: true, opacity: 0.22 })));
        moonPivots.push({ pivot: moonPivot, speed: m.speed });
      }

      mesh.userData = { spec, pivot, initialAngle: PLANETS.indexOf(spec) * 1.05 + 0.5 };
      pivot.rotation.y = mesh.userData.initialAngle as number;
      if (spec.id === "mercury" && process.env.NODE_ENV !== "production") {
        // dev: catch whoever writes a non-finite orbit angle (NaN rotation = black frame)
        let rotY = pivot.rotation.y;
        Object.defineProperty(pivot.rotation, "y", {
          get: () => rotY,
          set: (v: number) => {
            if (!isFinite(v) && !(window as unknown as { __rotStack?: string }).__rotStack) {
              (window as unknown as { __rotStack?: string }).__rotStack = new Error().stack || "";
            }
            rotY = isFinite(v) ? v : rotY; // refuse the NaN
          },
        });
      }
      interactive.push(mesh);
    }

    sunMesh.userData = { spec: SUN_SPEC };
    interactive.push(sunMesh);

    /* ── comets: icy nucleus + coma + 240-particle curved ion/dust tail ── */
    const comets: { group: THREE.Group; velocity: THREE.Vector3 }[] = [];
    const glowCyan = softDotTexture("150,215,255");
    const glowWarm = softDotTexture("255,228,175");
    for (let c = 0; c < 3; c++) {
      const group = new THREE.Group();
      // icy nucleus
      group.add(new THREE.Mesh(new THREE.SphereGeometry(0.55, 16, 16), new THREE.MeshBasicMaterial({ color: 0xf5fbff })));
      // layered coma: wide cyan halo + warm bright core (additive sprites)
      const comaOuter = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowCyan, color: 0x7fd4ff, transparent: true, opacity: 0.42, blending: THREE.AdditiveBlending, depthWrite: false }));
      comaOuter.scale.setScalar(9);
      const comaCore = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowWarm, color: 0xffe7c2, transparent: true, opacity: 0.8, blending: THREE.AdditiveBlending, depthWrite: false }));
      comaCore.scale.setScalar(3.4);
      group.add(comaOuter, comaCore);
      // dual tails: straight narrow ion + broad curved dust (soft round particles)
      const makeTail = (count: number, len: number, spread: number, curve: number, hex: number, size: number) => {
        const geo = new THREE.BufferGeometry();
        const pos = new Float32Array(count * 3);
        for (let i = 0; i < count; i++) {
          const t = Math.pow(Math.random(), 0.75);
          pos[i * 3] = (Math.random() - 0.5) * spread * t;
          pos[i * 3 + 1] = 2.5 + t * len;
          pos[i * 3 + 2] = (Math.random() - 0.5) * spread * t + t * t * curve;
        }
        geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
        return new THREE.Points(geo, new THREE.PointsMaterial({ size, map: starTex, color: hex, transparent: true, opacity: 0.5, blending: THREE.AdditiveBlending, depthWrite: false }));
      };
      group.add(makeTail(150, 62, 2.2, 0, 0x6fc4ff, 1.1));
      group.add(makeTail(110, 46, 6.5, 9, 0xffd9a0, 1.45));
      group.position.set((Math.random() - 0.5) * 500 + 120, Math.random() * 100 + 35, (Math.random() - 0.5) * 500 - 90);
      const velocity = new THREE.Vector3(-0.65 - Math.random() * 0.45, -0.2 - Math.random() * 0.15, 0.45 + Math.random() * 0.4);
      scene.add(group);
      comets.push({ group, velocity });
    }

    /* ── camera kinematics + interaction ── */
    scene.add(camera);
    const raycaster = new THREE.Raycaster();
    const mouse = new THREE.Vector2();
    let dragging = false;
    let prev = { x: 0, y: 0 };
    const spherical = { radius: 230, theta: 0.28, phi: 1.15 };
    const targetLookAt = new THREE.Vector3(0, 0, 0);
    const currentLookAt = new THREE.Vector3(0, 0, 0);
    let focused: THREE.Mesh | null = null;
    let simSpeed = 1.0;

    const onPointerDown = (e: PointerEvent) => {
      const t = e.target as HTMLElement;
      if (t.closest("button") || t.closest("a") || t.closest("[data-ui]") || t.closest(".public-nav")) return;
      dragging = true;
      prev = { x: e.clientX, y: e.clientY };
    };
    const onPointerMove = (e: PointerEvent) => {
      const rect = renderer.domElement.getBoundingClientRect();
      mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
      if (dragging) {
        spherical.theta -= (e.clientX - prev.x) * 0.004;
        spherical.phi = Math.max(0.12, Math.min(Math.PI / 2.05, spherical.phi - (e.clientY - prev.y) * 0.004));
        prev = { x: e.clientX, y: e.clientY };
      }
    };
    const onPointerUp = () => { dragging = false; };
    const onWheel = (e: WheelEvent) => {
      const t = e.target as HTMLElement;
      if (t.closest("[data-ui]") || t.closest(".public-nav")) return;
      spherical.radius = Math.max(20, Math.min(650, spherical.radius + e.deltaY * (focused ? 0.15 : 0.25)));
    };
    const onClick = (e: MouseEvent) => {
      const t = e.target as HTMLElement;
      if (t.closest("button") || t.closest("a") || t.closest("[data-ui]") || t.closest(".public-nav")) return;
      const rect = renderer.domElement.getBoundingClientRect();
      mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(mouse, camera);
      const hits = raycaster.intersectObjects(interactive);
      if (hits.length > 0) select(hits[0].object.userData.spec.id as string);
    };
    const onKeyDown = (e: KeyboardEvent) => { if (e.key === "Escape") resetView(); };
    const onResize = () => {
      const w = mount.clientWidth || window.innerWidth;
      const h = mount.clientHeight || window.innerHeight;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    };

    function select(id: string) {
      const found = interactive.find((p) => (p.userData.spec as PlanetSpec).id === id);
      if (!found) return;
      focused = found;
      spherical.theta = 0.35;
      spherical.phi = 1.25;
      window.dispatchEvent(new CustomEvent("planet-selected", { detail: found.userData.spec }));
    }
    function resetView() {
      focused = null;
      spherical.radius = 230;
      spherical.theta = 0.28;
      spherical.phi = 1.15;
      window.dispatchEvent(new CustomEvent("planet-deselected"));
    }
    function setWarp(speed: number) {
      if (!isFinite(speed)) {
        (window as unknown as { __warpStack?: string }).__warpStack = new Error().stack || "";
        speed = 1;
      }
      simSpeed = speed;
    }

    selectRef.current = select;
    resetRef.current = resetView;
    warpRef.current = setWarp;
    window.selectPlanet = select;
    window.resetCosmicView = resetView;
    window.setSimulationSpeed = setWarp;

    window.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
    window.addEventListener("wheel", onWheel, { passive: true });
    window.addEventListener("click", onClick);
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("resize", onResize);

    /* ── render loop ── */
    let raf = 0;
    const clock = new THREE.Clock();
    let raDecTick = 0;
    const raDecEl = () => document.getElementById("ra-dec-readout");

    // hoisted temporaries — the render loop allocates ZERO objects per frame
    // (per-frame `new THREE.Vector3` caused GC churn and visible jank)
    const _wp = new THREE.Vector3();
    const _v1 = new THREE.Vector3();
    const _v2 = new THREE.Vector3();
    const _v3 = new THREE.Vector3();
    const _offset = new THREE.Vector3();
    const _side = new THREE.Vector3();
    const _up = new THREE.Vector3(0, 1, 0);
    const _origin = new THREE.Vector3(0, 0, 0);

    function animate() {
      raf = requestAnimationFrame(animate);
      try {
      if (document.hidden) return;
      // self-heal: a single NaN poisons every lerp forever — snap back to orbit
      const w = window as unknown as { __frames?: number; __cam?: number[]; __tgt?: number[]; __nanAt?: string; __nanPlanet?: string; __nanPrev?: unknown };
      if (!isFinite(camera.position.x + camera.position.y + camera.position.z)
          || !isFinite(currentLookAt.x + currentLookAt.y + currentLookAt.z)) {
        if (!w.__nanAt) {
          (window as unknown as { __nanPrev?: unknown }).__nanPrev = w.__cam ? { cam: w.__cam, tgt: w.__tgt } : null;
          w.__nanAt = focused ? `inspect:${(focused.userData.spec as PlanetSpec).id}` : "overview";
        }
        spherical.radius = 230; spherical.theta = 0.28; spherical.phi = 1.15;
        camera.position.set(0, 95, 230);
        currentLookAt.set(0, 0, 0);
        targetLookAt.set(0, 0, 0);
        focused = null;
        window.dispatchEvent(new CustomEvent("planet-deselected"));
      }
      const time = clock.getElapsedTime();

      systemGroup.rotation.y += 0.00035 * simSpeed; // the plane drifts across the galaxy
      sunAnchor.position.set(Math.cos(time * 0.06) * 2.6, Math.sin(time * 0.045) * 1.5, Math.sin(time * 0.06) * 2.6);
      sunMesh.rotation.y += 0.003 * simSpeed;
      const pulse = 1 + Math.sin(time * 2.5) * 0.035;
      coronaMesh.scale.setScalar(pulse);
      flareMesh.rotation.z += 0.002 * simSpeed;
      galaxyGroup.rotation.y += 0.00025 * simSpeed; // we rotate around the Milky Way
      farGalaxies.rotation.y += 0.00004 * simSpeed; // the deep field drifts with us

      // the starfield itself drifts and twinkles around its theme baseline
      starGroup.rotation.y += 0.00002 * simSpeed;
      for (let i = 0; i < starMats.length; i++) {
        starMats[i].opacity = starBase[i] * (0.96 + Math.sin(time * 1.1 + i * 2.1) * 0.04);
      }

      for (const p of interactive) {
        const ud = p.userData as { pivot?: THREE.Group; spec: PlanetSpec };
        if (ud.pivot) ud.pivot.rotation.y += ud.spec.speed * simSpeed; // the sun has no orbit
        p.rotation.y += 0.008 * simSpeed;
      }
      for (const m of moonPivots) m.pivot.rotation.y += m.speed * simSpeed;

      // NaN hunt: which planet's matrix goes non-finite first?
      for (const p of interactive) {
        p.getWorldPosition(_v1);
        if (!isFinite(_v1.x + _v1.y + _v1.z)) {
          const id = (p.userData.spec as PlanetSpec).id;
          if (!w.__nanPlanet) w.__nanPlanet = id;
          const pivot = p.parent as THREE.Group;
          pivot.rotation.set(0, (p.userData.spec as PlanetSpec).distance * 0.01, 0); // heal the orbit
          p.rotation.set(0, 0, 0);
        }
      }

      for (const c of comets) {
        _v1.copy(c.velocity).multiplyScalar(simSpeed);
        c.group.position.add(_v1);
        if (c.group.position.x < -480 || c.group.position.y < -140 || c.group.position.z > 480) {
          c.group.position.set(Math.random() * 420 + 140, Math.random() * 120 + 40, (Math.random() - 0.5) * 420 - 90);
        }
        // radiation pressure: tails always point away from the sun
        _v2.copy(c.group.position).normalize();
        c.group.quaternion.setFromUnitVectors(_up, _v2);
      }

      if (focused) {
        focused.getWorldPosition(_wp);
        targetLookAt.lerp(_wp, 0.12);
        const fSpec = focused.userData.spec as PlanetSpec;
        camFill.intensity = fSpec.id === "sol" ? 0 : 0.55;
        const zoomDist = fSpec.id === "sol" ? fSpec.radius * 4.6 + 14 : fSpec.radius * 3.4 + 10.5;
        // fly to the SUNWARD side of the planet: the lit hemisphere faces the sun,
        // so the camera sits between sun and planet — full 3/4 lit phase with depth
        _v2.copy(_wp).setY(_wp.y * 0.25);
        const towardSun = _v2.lengthSq() > 1e-6 ? _v2.normalize().negate() : _v2.set(0, 0, -1);
        _side.set(-towardSun.z, 0, towardSun.x);
        _offset.copy(towardSun).multiplyScalar(zoomDist * 0.92)
          .add(_side.multiplyScalar(zoomDist * 0.42))
          .add(_v3.set(0, zoomDist * 0.3, 0));
        camera.position.lerp(_v1.copy(_wp).add(_offset), 0.08);
      } else {
        targetLookAt.lerp(_origin, 0.06);
        camera.position.lerp(_v1.set(
          spherical.radius * Math.sin(spherical.phi) * Math.sin(spherical.theta),
          spherical.radius * Math.cos(spherical.phi),
          spherical.radius * Math.sin(spherical.phi) * Math.cos(spherical.theta)
        ), 0.08);
      }
      currentLookAt.lerp(targetLookAt, 0.1);
      camera.lookAt(currentLookAt);

      // RA/DEC readout from camera angles (every ~12 frames)
      if (++raDecTick % 12 === 0) {
        const el = raDecEl();
        if (el) {
          const ra = ((spherical.theta / (Math.PI * 2)) * 24 + 24) % 24;
          const dec = 90 - (spherical.phi * 180) / Math.PI;
          el.textContent = `RA: ${String(Math.floor(ra)).padStart(2, "0")}h ${String(Math.floor((ra % 1) * 60)).padStart(2, "0")}m ${String(Math.floor((((ra * 60) % 1) * 60))).padStart(2, "0")}s   DEC: ${dec >= 0 ? "+" : "−"}${Math.abs(dec).toFixed(0)}° ${String(Math.floor((Math.abs(dec) % 1) * 60)).padStart(2, "0")}′`;
        }
      }

      renderer.render(scene, camera);
      w.__frames = (w.__frames || 0) + 1;
      w.__cam = [camera.position.x, camera.position.y, camera.position.z];
      w.__tgt = [currentLookAt.x, currentLookAt.y, currentLookAt.z];
      } catch (err) {
        (window as unknown as { __animErr?: string }).__animErr = String((err as Error)?.stack || err);
        throw err;
      }
    }
    raf = requestAnimationFrame(animate);

    return () => {
      cancelAnimationFrame(raf);
      themeObserver.disconnect();
      window.removeEventListener("pointerdown", onPointerDown);
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
      window.removeEventListener("wheel", onWheel);
      window.removeEventListener("click", onClick);
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("resize", onResize);
      renderer.dispose();
      if (renderer.domElement.parentElement === mount) mount.removeChild(renderer.domElement);
    };
  }, []);

  useEffect(() => {
    const onSel = (e: Event) => { setSelected((e as CustomEvent).detail as PlanetSpec); setHeroHidden(true); };
    const onDesel = () => { setSelected(null); setHeroHidden(false); };
    window.addEventListener("planet-selected", onSel);
    window.addEventListener("planet-deselected", onDesel);
    return () => {
      window.removeEventListener("planet-selected", onSel);
      window.removeEventListener("planet-deselected", onDesel);
    };
  }, []);

  const doWarp = useCallback((s: number) => { setWarp(s); warpRef.current(s); }, []);

  return (
    <>
      {!mounted && (
        <div className="solsys-loading">
          <span className="label label--accent">◌ aligning the sky…</span>
        </div>
      )}
      <div ref={mountRef} className="solsys-mount" />

      {/* top status chips */}
      <div className="cosmos-topbar" data-ui>
        <span className="chip pointer-events-auto">◉ SKY MAP REAL-TIME ENGINE · {PLANETS.length + 1} MODULES ACTIVE</span>
        <span className="chip chip-row">
          WARP
          {[0.5, 1, 2, 5].map((s) => (
            <button key={s} onClick={() => doWarp(s)}
                    className={`mono-chip ${warp === s ? "on" : ""}`}
                    aria-pressed={warp === s}>{s}x</button>
          ))}
        </span>
      </div>

      {/* hero card — fades during inspection */}
      <div className={`solsys-hero ${heroHidden ? "hero-hidden" : ""}`} data-ui>
        <span className="label label--accent">ASTRAEA · THE STAR-MAIDEN WHO CAME BACK</span>
        <h1 className="display serif">Astraea.</h1>
        <p className="hero-lead">
          Six agents that do the <span className="hl">work of humans</span> — watched, approved
          and remembered. One shared brain. Offline on your machine. The same build on Vertex AI and any cloud.
        </p>
        <div className="hero-actions">
          <Link href="/login" className="btn btn--accent">RESERVE A WORKSPACE →</Link>
          <Link href="/docs" className="btn btn--ghost">◉ SEE THE SKY MAP</Link>
        </div>
        <p className="label" style={{ marginTop: 14, color: "var(--ink-30)" }}>
          CLICK A PLANET OR DOCK TO ZOOM IN · {PLANETS.length + 1} PRODUCT CORES ACTIVE
        </p>
      </div>

      {/* inspection drawer */}
      {selected && (
        <aside className="planet-drawer" role="dialog" aria-label={`${selected.module} details`} data-ui>
          <div className="drawer-head">
            <span className="label label--accent">{selected.name.toUpperCase()} · {selected.module}</span>
            <button className="drawer-x" onClick={() => resetRef.current()} aria-label="return to orbit">✕</button>
          </div>
          <h2 className="display" style={{ fontSize: 22, margin: "6px 0 2px" }}>{selected.title}</h2>
          <p className="label" style={{ color: "var(--ink-50)", marginBottom: 10 }}>{selected.category}</p>
          <p style={{ fontSize: 13.5, color: "var(--ink-70)", lineHeight: 1.65, margin: "0 0 12px" }}>{selected.description}</p>

          {selected.fusion ? (
            <div className="nasa-grid">
              <div><span className="k">TESTS</span><span className="v">110/110 ✅</span></div>
              <div><span className="k">SELF-TEST</span><span className="v">7 PATHS · OK</span></div>
              <div><span className="k">WATCHDOG</span><span className="v">30 s SELF-HEAL</span></div>
              <div><span className="k">RUNTIME</span><span className="v">EVENT-SOURCED</span></div>
            </div>
          ) : (
            <div className="nasa-grid">
              <div><span className="k">DISTANCE FROM SUN</span><span className="v">{selected.au}</span></div>
              <div><span className="k">ORBITAL VELOCITY</span><span className="v">{selected.velocity}</span></div>
              <div><span className="k">DAY LENGTH</span><span className="v">{selected.day}</span></div>
              <div><span className="k">AXIAL TILT</span><span className="v">{selected.tilt}</span></div>
            </div>
          )}

          <p className="label label--ink" style={{ margin: "12px 0 6px" }}>MODULE FEATURES</p>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 12 }}>
            {selected.features.map((f) => <span key={f} className="stamp stamp--shared">{f}</span>)}
          </div>

          {selected.fusion ? (
            <>
              <p className="label label--ink" style={{ margin: "0 0 6px" }}>ALL MODULES — FUSION ACTIVE</p>
              <div className="fusion-grid">
                {PLANETS.map((m) => (
                  <Link key={m.id} href={m.workbench} className="fusion-cell">
                    <span className={`dock-dot dot-${m.id}`} />
                    <b>{m.module}</b>
                    <i>{m.title}</i>
                  </Link>
                ))}
              </div>
            </>
          ) : (
            <>
              <p className="label label--ink" style={{ margin: "0 0 6px" }}>NATURAL SATELLITES · ACTIVE</p>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 12 }}>
                {selected.moons.map((m) => <span key={m.name} className="stamp stamp--used" title={m.note}>{m.name}</span>)}
              </div>
            </>
          )}

          <p className="label" style={{ color: "var(--ink-50)", margin: "0 0 12px" }}>{selected.specs}</p>

          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <Link href={selected.docs} className="btn btn--accent" style={{ fontSize: 12 }}>READ FEATURE DOCS →</Link>
            <Link href={selected.workbench} className="btn btn--ghost" style={{ fontSize: 12 }}>OPEN WORKBENCH</Link>
          </div>
        </aside>
      )}

      {/* bottom dock */}
      <div className="planet-dock" data-ui>
        <button className={`dock-item ${selected?.id === "sol" ? "active" : ""}`}
                onClick={() => selectRef.current("sol")}>
          <span className="dock-dot dot-sol" />
          <span><b>☉ FUSION</b><i>all modules</i></span>
        </button>
        {PLANETS.map((p) => (
          <button key={p.id} className={`dock-item ${selected?.id === p.id ? "active" : ""}`}
                  onClick={() => selectRef.current(p.id)}>
            <span className={`dock-dot dot-${p.id}`} />
            <span><b>{p.module}</b><i>{p.name}</i></span>
          </button>
        ))}
        <button className="dock-item dock-full" onClick={() => resetRef.current()}>
          <span><b>∞ FULL ORBIT</b></span>
        </button>
      </div>

      <div className="ra-dec" data-ui>
        <span id="ra-dec-readout">RA: 18h 36m 56s DEC: +38° 47′</span>
        <span className="ra-dec-live">MILKY WAY DRIFT: ACTIVE</span>
      </div>
    </>
  );
}
