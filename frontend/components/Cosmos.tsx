"use client";

/**
 * Observatory sky: earth + moon drift across the field, thin meteors
 * from random edges. No sun sprite. Lighting stays on the sphere.
 */
import { useEffect, useRef } from "react";

function rand(min: number, max: number) {
  return min + Math.random() * (max - min);
}

type Wanderer = {
  el: HTMLElement;
  x: number;
  y: number;
  vx: number;
  vy: number;
  speed: number;
};

function kick(b: Wanderer) {
  const a = rand(0, Math.PI * 2);
  b.vx = Math.cos(a) * b.speed;
  b.vy = Math.sin(a) * b.speed;
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

export function Cosmos() {
  const earthRef = useRef<HTMLDivElement>(null);
  const moonRef = useRef<HTMLDivElement>(null);
  const cometRefs = useRef<(HTMLSpanElement | null)[]>([null, null]);

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    const timeouts: number[] = [];
    const bodies: Wanderer[] = [];
    if (earthRef.current) {
      bodies.push({
        el: earthRef.current,
        x: rand(52, 78),
        y: rand(10, 32),
        vx: 0,
        vy: 0,
        speed: rand(3.6, 6.2),
      });
    }
    if (moonRef.current) {
      bodies.push({
        el: moonRef.current,
        x: rand(6, 28),
        y: rand(48, 72),
        vx: 0,
        vy: 0,
        speed: rand(5.2, 8.8),
      });
    }
    for (const b of bodies) {
      kick(b);
      b.el.style.transform = `translate3d(${b.x}vw, ${b.y}vh, 0)`;
    }

    const scheduleKick = (b: Wanderer) => {
      const id = window.setTimeout(() => {
        kick(b);
        scheduleKick(b);
      }, rand(4200, 11000));
      timeouts.push(id);
    };
    bodies.forEach(scheduleKick);

    let last = performance.now();
    let raf = 0;
    const tick = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      for (const b of bodies) {
        b.x += b.vx * dt;
        b.y += b.vy * dt;
        let bounced = false;
        if (b.x < 4 || b.x > 86) {
          b.x = Math.min(86, Math.max(4, b.x));
          bounced = true;
        }
        if (b.y < 6 || b.y > 78) {
          b.y = Math.min(78, Math.max(6, b.y));
          bounced = true;
        }
        if (bounced) kick(b);
        b.el.style.transform = `translate3d(${b.x}vw, ${b.y}vh, 0)`;
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);

    let cancelled = false;
    const scheduleComet = (el: HTMLElement, delay: number) => {
      const id = window.setTimeout(() => {
        if (cancelled) return;
        const dur = launchComet(el);
        scheduleComet(el, dur * 1000 + rand(2200, 7800));
      }, delay);
      timeouts.push(id);
    };
    cometRefs.current.forEach((el, i) => {
      if (el) scheduleComet(el, 900 + i * rand(1600, 3200));
    });

    return () => {
      cancelled = true;
      cancelAnimationFrame(raf);
      timeouts.forEach((id) => window.clearTimeout(id));
    };
  }, []);

  return (
    <div className="cosmos" aria-hidden>
      <div className="cosmos-sky-wrap">
        <img className="cosmos-sky" src="/cosmos/milkyway.png" alt="" />
        <span className="cosmos-stars" />
        <span className="cosmos-sky-veil" />
      </div>
      <div ref={earthRef} className="cosmos-body cosmos-earth">
        <span className="cosmos-body-globe">
          <img className="cosmos-body-tex" src="/cosmos/earth.png" alt="" />
          <span className="cosmos-body-shade" />
        </span>
      </div>
      <div ref={moonRef} className="cosmos-body cosmos-moon">
        <span className="cosmos-body-globe">
          <img className="cosmos-body-tex" src="/cosmos/moon.png" alt="" />
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
  );
}
