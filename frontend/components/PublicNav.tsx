"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { ThemeToggle } from "./ThemeToggle";

const LINKS = [
  { href: "/", label: "Home" },
  { href: "/pricing", label: "Pricing" },
  { href: "/docs", label: "Docs" },
  { href: "/blog", label: "Blog" },
  { href: "/contact", label: "Contact" },
  { href: "/faq", label: "FAQ" },
  { href: "/about", label: "About" },
];

export function PublicNav() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  useEffect(() => { setOpen(false); }, [pathname]);

  return (
    <header className={`public-nav ${open ? "is-open" : ""}`}>
      <Link href="/" className="wordmark" style={{ fontSize: 15 }}>
        ASTRAEA<em>.</em>
      </Link>
      <nav id="public-links" className="public-links">
        {LINKS.map((l) => {
          const active = l.href === "/" ? pathname === "/" : pathname.startsWith(l.href);
          return (
            <Link key={l.href} href={l.href}
                  className={active ? "nav-active" : ""}
                  style={active ? { color: "var(--accent)", boxShadow: "inset 0 -2px 0 var(--accent)" } : {}}>
              {l.label}
            </Link>
          );
        })}
        <Link href="/login" className="drawer-signin">Sign in →</Link>
      </nav>
      <div className="public-nav-end">
        <ThemeToggle />
        <Link href="/login" className="btn btn--accent nav-signin">Sign in →</Link>
        <button
          type="button"
          className="nav-burger"
          aria-expanded={open}
          aria-controls="public-links"
          onClick={() => setOpen((v) => !v)}
        >
          {open ? "Close" : "Menu"}
        </button>
      </div>
    </header>
  );
}
