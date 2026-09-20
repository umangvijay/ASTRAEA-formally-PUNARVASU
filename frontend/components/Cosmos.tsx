"use client";

/**
 * Observatory sky: solar-system globes wander the field.
 * Earth + moon (and the other planets) can be dragged; drag spins them.
 * No .cosmos-sun class — the star is .cosmos-sol.
 */
import { useEffect, useRef } from "react";

function rand(min: number, max: number) {
  return min + Math.random() * (max - min);
}

type Body = {
  el: HTMLElement;
  tex: HTMLElement | null;
  globe: HTMLElement | null;
  x: number;
  y: number;
  vx: number;
  vy: number;
  speed: number;
  spin: number;
  spinVel: number;
  autoSpin: number;
  tilt: number;
  yaw: number;
  draggable: boolean;
  dragging: boolean;
  lastPx: number;
  lastPy: number;
  throwVx: number;
  throwVy: number;
};

function kick(b: Body) {
  const a = rand(0, Math.PI * 2);
  b.vx = Math.cos(a) * b.speed;
  b.vy = Math.sin(a) * b.speed;
}

function apply(b: Body) {
  b.el.style.transform = `translate3d(${b.x}vw, ${b.y}vh, 0)`;
  if (b.tex) b.tex.style.transform = `rotate(${b.spin}deg)`;
  if (b.globe) {
    b.globe.style.transform = `rotateX(${b.tilt}deg) rotateY(${b.yaw}deg)`;
  }
}

function launchComet(el: HTMLElement) {
  const edge = Math.floor(rand(0, 4));
  let x: number;
  let y: number;
  let heading: number;
  if (edge === 0) {
    x = rand(8, 92);
    y = -10;
    heading = rand(Math.PI * 0.18, Math.PI * 0.82);
  } else if (edge === 1) {
    x = 110;
    y = rand(6, 90);
    heading = rand(Math.PI * 0.68, Math.PI * 1.32);
  } else if (edge === 2) {
    x = rand(8, 92);
    y = 110;
    heading = rand(-Math.PI * 0.82, -Math.PI * 0.18);
  } else {
    x = -10;
    y = rand(6, 90);
    heading = rand(-Math.PI * 0.32, Math.PI * 0.32);
  }
  const dist = rand(72, 128);
  const dur = rand(0.9, 2.15);
  el.style.setProperty("--cx", `${x}vw`);
  el.style.setProperty("--cy", `${y}vh`);
  el.style.setProperty("--dx", `${x + Math.cos(heading) * dist}vw`);
  el.style.setProperty("--dy", `${y + Math.sin(heading) * dist}vh`);
  el.style.setProperty("--rot", `${(heading * 180) / Math.PI}deg`);
  el.style.setProperty("--dur", `${dur}s`);
  el.classList.remove("is-flying");
  void el.offsetWidth;
  el.classList.add("is-flying");
  return dur;
}

const START: { id: string; x: number; y: number; speed: number; autoSpin: number; draggable: boolean }[] = [
  { id: "sol", x: 88, y: 6, speed: 0.55, autoSpin: 8, draggable: false },
  { id: "mercury", x: 83, y: 22, speed: 7.4, autoSpin: 14, draggable: true },
  { id: "venus", x: 74, y: 40, speed: 5.1, autoSpin: 6, draggable: true },
  { id: "earth", x: 62, y: 10, speed: 4.4, autoSpin: 4, draggable: true },
  { id: "moon", x: 56, y: 44, speed: 6.8, autoSpin: 3, draggable: true },
  { id: "mars", x: 68, y: 62, speed: 5.8, autoSpin: 7, draggable: true },
  { id: "jupiter", x: 42, y: 70, speed: 3.2, autoSpin: 11, draggable: true },
  { id: "saturn", x: 81, y: 72, speed: 3.6, autoSpin: 9, draggable: true },
  { id: "neptune", x: 10, y: 66, speed: 4.0, autoSpin: 5, draggable: true },
];

export function Cosmos({ ambient = false }: { ambient?: boolean }) {
  const bodyRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const cometRefs = useRef<(HTMLSpanElement | null)[]>([null, null]);

  useEffect(() => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const timeouts: number[] = [];
    const bodies: Body[] = [];
    const vw = () => window.innerWidth || 1;
    const vh = () => window.innerHeight || 1;

    // ambient mode: sky, stars, nebulas and comets only — no draggable bodies,
    // no RAF loop (inner pages keep the home theme without the scene weight)
    for (const spec of ambient ? [] : START) {
      const el = bodyRefs.current[spec.id];
      if (!el) continue;
      const tex = el.querySelector<HTMLElement>(".cosmos-body-tex");
      const globe = el.querySelector<HTMLElement>(".cosmos-body-globe");
      if (tex) tex.style.animation = "none";
      const b: Body = {
        el,
        tex,
        globe,
        x: spec.x,
        y: spec.y,
        vx: 0,
        vy: 0,
        speed: spec.speed,
        spin: rand(0, 360),
        spinVel: spec.autoSpin,
        autoSpin: spec.autoSpin,
        tilt: rand(-6, 12),
        yaw: rand(-10, 10),
        draggable: spec.draggable,
        dragging: false,
        lastPx: 0,
        lastPy: 0,
        throwVx: 0,
        throwVy: 0,
      };
      if (!reduce) kick(b);
      apply(b);
      bodies.push(b);

      if (!b.draggable) continue;
      el.style.cursor = "grab";
      el.style.touchAction = "pan-y";

      const down = (ev: PointerEvent) => {
        if (ev.button !== 0 && ev.pointerType === "mouse") return;
        ev.preventDefault();
        b.dragging = true;
        b.vx = 0;
        b.vy = 0;
        b.throwVx = 0;
        b.throwVy = 0;
        b.lastPx = ev.clientX;
        b.lastPy = ev.clientY;
        el.setPointerCapture(ev.pointerId);
        el.classList.add("is-dragging");
        el.style.cursor = "grabbing";
        el.style.touchAction = "none";
      };
      const move = (ev: PointerEvent) => {
        if (!b.dragging) return;
        const dx = ev.clientX - b.lastPx;
        const dy = ev.clientY - b.lastPy;
        b.lastPx = ev.clientX;
        b.lastPy = ev.clientY;
        b.x += (dx / vw()) * 100;
        b.y += (dy / vh()) * 100;
        b.x = Math.min(88, Math.max(1, b.x));
        b.y = Math.min(82, Math.max(2, b.y));
        b.spin += dx * 0.55;
        b.spinVel = dx * 12;
        b.yaw = Math.max(-42, Math.min(42, b.yaw + dx * 0.18));
        b.tilt = Math.max(-28, Math.min(32, b.tilt - dy * 0.16));
        b.throwVx = (dx / vw()) * 100 * 18;
        b.throwVy = (dy / vh()) * 100 * 18;
        apply(b);
      };
      const up = (ev: PointerEvent) => {
        if (!b.dragging) return;
        b.dragging = false;
        el.classList.remove("is-dragging");
        el.style.cursor = "grab";
        el.style.touchAction = "pan-y";
        try { el.releasePointerCapture(ev.pointerId); } catch { /* already released */ }
        b.vx = b.throwVx;
        b.vy = b.throwVy;
        const mag = Math.hypot(b.vx, b.vy);
        if (mag > 42) {
          const s = 42 / mag;
          b.vx *= s;
          b.vy *= s;
        }
        if (mag < 2 && !reduce) kick(b);
      };
      el.addEventListener("pointerdown", down);
      el.addEventListener("pointermove", move);
      el.addEventListener("pointerup", up);
      el.addEventListener("pointercancel", up);
      timeouts.push(0);
      (b as Body & { _off?: () => void })._off = () => {
        el.removeEventListener("pointerdown", down);
        el.removeEventListener("pointermove", move);
        el.removeEventListener("pointerup", up);
        el.removeEventListener("pointercancel", up);
      };
    }

    let last = performance.now();
    let raf = 0;
    const tick = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      for (const b of bodies) {
        if (b.dragging) continue;
        if (reduce) continue;
        b.x += b.vx * dt;
        b.y += b.vy * dt;
        let bounced = false;
        if (b.x < 2 || b.x > 88) {
          b.x = Math.min(88, Math.max(2, b.x));
          bounced = true;
        }
        if (b.y < 4 || b.y > 80) {
          b.y = Math.min(80, Math.max(4, b.y));
          bounced = true;
        }
        if (bounced) kick(b);
        b.spin += b.spinVel * dt;
        b.spinVel += (b.autoSpin - b.spinVel) * Math.min(1, dt * 0.7);
        b.yaw += (0 - b.yaw) * Math.min(1, dt * 0.35);
        apply(b);
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);

    const scheduleKick = (b: Body) => {
      const id = window.setTimeout(() => {
        if (!b.dragging && !reduce) kick(b);
        scheduleKick(b);
      }, rand(5000, 14000));
      timeouts.push(id);
    };
    if (!reduce) bodies.forEach(scheduleKick);

    let cancelled = false;
    const scheduleComet = (el: HTMLElement, delay: number) => {
      const id = window.setTimeout(() => {
        if (cancelled || reduce) return;
        const dur = launchComet(el);
        scheduleComet(el, dur * 1000 + rand(2200, 7800));
      }, delay);
      timeouts.push(id);
    };
    cometRefs.current.forEach((el, i) => {
      if (el && !reduce) scheduleComet(el, 900 + i * rand(1600, 3200));
    });

    return () => {
      cancelled = true;
      cancelAnimationFrame(raf);
      timeouts.forEach((id) => { if (id) window.clearTimeout(id); });
      bodies.forEach((b) => {
        const off = (b as Body & { _off?: () => void })._off;
        off?.();
      });
    };
  }, []);

  const setRef = (id: string) => (n: HTMLDivElement | null) => {
    bodyRefs.current[id] = n;
  };

  return (
    <>
      <div className={`cosmos${ambient ? " cosmos--ambient" : ""}`} aria-hidden>
        <div className="cosmos-sky-wrap">
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
      {!ambient && (
      <div className="cosmos-bodies" aria-hidden>
        <div ref={setRef("sol")} className="cosmos-body cosmos-sol">
          <span className="cosmos-sol-core" />
        </div>
        <div ref={setRef("mercury")} className="cosmos-body cosmos-planet cosmos-mercury">
          <span className="cosmos-body-globe">
            <img className="cosmos-body-tex" src="/cosmos/mercury.png" alt="" />
            <span className="cosmos-body-shade" />
          </span>
        </div>
        <div ref={setRef("venus")} className="cosmos-body cosmos-planet cosmos-venus">
          <span className="cosmos-body-globe">
            <img className="cosmos-body-tex" src="/cosmos/venus.png" alt="" />
            <span className="cosmos-body-shade" />
          </span>
        </div>
        <div ref={setRef("earth")} className="cosmos-body cosmos-earth">
          <span className="cosmos-body-globe">
            <img className="cosmos-body-tex" src="/cosmos/earth.png" alt="" />
            <span className="cosmos-body-shade" />
          </span>
        </div>
        <div ref={setRef("moon")} className="cosmos-body cosmos-moon">
          <span className="cosmos-body-globe">
            <img className="cosmos-body-tex" src="/cosmos/moon.png" alt="" />
            <span className="cosmos-body-shade" />
          </span>
        </div>
        <div ref={setRef("mars")} className="cosmos-body cosmos-planet cosmos-mars">
          <span className="cosmos-body-globe">
            <img className="cosmos-body-tex" src="/cosmos/mars.png" alt="" />
            <span className="cosmos-body-shade" />
          </span>
        </div>
        <div ref={setRef("jupiter")} className="cosmos-body cosmos-planet cosmos-jupiter">
          <span className="cosmos-body-globe">
            <img className="cosmos-body-tex" src="/cosmos/jupiter.png" alt="" />
            <span className="cosmos-body-shade" />
          </span>
        </div>
        <div ref={setRef("saturn")} className="cosmos-body cosmos-planet cosmos-saturn">
          <span className="cosmos-saturn-ring" />
          <span className="cosmos-body-globe">
            <img className="cosmos-body-tex" src="/cosmos/saturn.png" alt="" />
            <span className="cosmos-body-shade" />
          </span>
        </div>
        <div ref={setRef("neptune")} className="cosmos-body cosmos-planet cosmos-neptune">
          <span className="cosmos-body-globe">
            <img className="cosmos-body-tex" src="/cosmos/neptune.png" alt="" />
            <span className="cosmos-body-shade" />
          </span>
        </div>
        <span className="cosmos-comet" ref={(n) => { cometRefs.current[0] = n; }}>
          <span className="cosmos-comet-dust" />
          <span className="cosmos-comet-ion" />
          <span className="cosmos-comet-head" />
        </span>
        <span className="cosmos-comet cosmos-comet--b" ref={(n) => { cometRefs.current[1] = n; }}>
          <span className="cosmos-comet-dust" />
          <span className="cosmos-comet-ion" />
          <span className="cosmos-comet-head" />
        </span>
      </div>
      )}
    </>
  );
}
