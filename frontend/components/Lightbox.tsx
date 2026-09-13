"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

export type Plate = {
  id: string;
  title: string;
  caption: string;
  image: string;
  href: string;
};

export function LightboxGrid({ plates }: { plates: Plate[] }) {
  const [open, setOpen] = useState<Plate | null>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(null); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <>
      <div className="plate-grid">
        {plates.map((p) => (
          <article key={p.id} className="plate glass-card">
            <button type="button" className="plate-hit" onClick={() => setOpen(p)} aria-label={`Open ${p.title}`}>
              <img className="plate-art" src={p.image} alt={p.title} width={640} height={400} />
            </button>
            <div className="plate-cap">
              <Link href={p.href} className="label label--accent">
                {p.title}
              </Link>
              <p>{p.caption}</p>
            </div>
          </article>
        ))}
      </div>
      {open && (
        <div className="lightbox" onClick={() => setOpen(null)} role="dialog" aria-modal>
          <figure className="lightbox-card glass-elevated" onClick={(e) => e.stopPropagation()}>
            <img className="plate-art plate-art--lg" src={open.image} alt={open.title} width={960} height={600} />
            <figcaption className="plate-cap">
              <span className="label label--accent">{open.title}</span>
              <p>{open.caption}</p>
            </figcaption>
            <div style={{ display: "flex", gap: 10, marginTop: 12 }}>
              <Link href={open.href} className="btn btn--accent">Read the docs →</Link>
              <button className="btn btn--ghost" type="button" onClick={() => setOpen(null)}>Close</button>
            </div>
          </figure>
        </div>
      )}
    </>
  );
}
