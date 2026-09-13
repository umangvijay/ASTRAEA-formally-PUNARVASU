"use client";

/**
 * Observatory sky: 3D earth + moon drift on random headings, comets
 * from random edges. No sun sprite (the painted burst is veined out).
 * Texture spins on the sphere; lighting stays put.
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
  xmin: number;
  xmax: number;
  ymin: number;
  ymax: number;
};

function kick(b: Wanderer) {
  const speed = b.speed * rand(0.55, 1.25);
  const a = rand(0, Math.PI * 2);
  b.vx = Math.cos(a) * speed;
  b.vy = Math.sin(a) * speed;
}

function launchComet(el: HTMLElement) {
  const edge = Math.floor(rand(0, 4));
  let x: number;
  let y: number;
  if (edge === 0) {
    x = rand(-8, 108);
    y = -18;
  } else if (edge === 1) {
    x = 112;
    y = rand(-8, 108);
  } else if (edge === 2) {
    x = rand(-8, 108);
    y = 112;
  } else {
    x = -18;
    y = rand(-8, 108);
  }
  const heading = rand(0, Math.PI * 2);
  const dist = rand(120, 190);
  const dur = rand(2.6, 7.2);
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
  const cometRefs = useRef<(HTMLSpanElement | null)[]>([null, null, null]);

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    const timeouts: number[] = [];
    const bodies: Wanderer[] = [];
    if (earthRef.current) {
      bodies.push({
        el: earthRef.current,
        x: rand(84, 90),
        y: rand(14, 20),
        vx: 0,
        vy: 0,
        speed: rand(0.01, 0.018),
        xmin: 82,
        xmax: 91,
        ymin: 12,
        ymax: 22,
      });
    }
    if (moonRef.current) {
      bodies.push({
        el: moonRef.current,
        x: rand(4, 10),
        y: rand(70, 78),
        vx: 0,
        vy: 0,
        speed: rand(0.014, 0.024),
        xmin: 3,
        xmax: 14,
        ymin: 66,
        ymax: 82,
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
      }, rand(2800, 8200));
      timeouts.push(id);
    };
    bodies.forEach(scheduleKick);

    let raf = 0;
    const tick = () => {
      for (const b of bodies) {
        b.x += b.vx;
        b.y += b.vy;
        if (b.x < b.xmin || b.x > b.xmax) {
          b.vx *= -1;
          b.x = Math.min(b.xmax, Math.max(b.xmin, b.x));
        }
        if (b.y < b.ymin || b.y > b.ymax) {
          b.vy *= -1;
          b.y = Math.min(b.ymax, Math.max(b.ymin, b.y));
        }
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
        scheduleComet(el, dur * 1000 + rand(500, 2800));
      }, delay);
      timeouts.push(id);
    };
    cometRefs.current.forEach((el, i) => {
      if (el) scheduleComet(el, 400 + i * rand(700, 1600));
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
        <span className="cosmos-sky-veil" />
      </div>
      <div ref={earthRef} className="cosmos-body cosmos-earth">
        <img className="cosmos-body-tex" src="/cosmos/earth.png" alt="" />
        <span className="cosmos-body-shade" />
      </div>
      <div ref={moonRef} className="cosmos-body cosmos-moon">
        <img className="cosmos-body-tex" src="/cosmos/moon.png" alt="" />
        <span className="cosmos-body-shade" />
      </div>
      <span className="cosmos-comet" ref={(n) => { cometRefs.current[0] = n; }} />
      <span className="cosmos-comet cosmos-comet--b" ref={(n) => { cometRefs.current[1] = n; }} />
      <span className="cosmos-comet cosmos-comet--c" ref={(n) => { cometRefs.current[2] = n; }} />
    </div>
  );
}
