"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
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
  return (
    <header className="public-nav">
      <Link href="/" className="wordmark" style={{ fontSize: 15 }}>
        ASTRAEA<em>.</em>
      </Link>
      <nav>
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
      </nav>
      <div style={{ flex: 1 }} />
      <ThemeToggle />
      <Link href="/login" className="btn btn--accent" style={{ padding: "7px 16px" }}>Sign in →</Link>
    </header>
  );
}
