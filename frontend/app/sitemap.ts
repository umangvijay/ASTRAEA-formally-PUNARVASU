import type { MetadataRoute } from "next";

const ORIGIN =
  process.env.ASTRAEA_PUBLIC_CONSOLE_URL
  || process.env.NEXT_PUBLIC_SITE_URL
  || "https://astraea-console-714727365323.us-central1.run.app";

export default function sitemap(): MetadataRoute.Sitemap {
  const paths = [
    "",
    "/login",
    "/pricing",
    "/docs",
    "/docs/architecture",
    "/docs/deploy",
    "/docs/medic",
    "/docs/operator",
    "/docs/shield",
    "/docs/vaani",
    "/docs/forge",
    "/docs/security",
    "/about",
    "/contact",
    "/faq",
    "/blog",
    "/privacy",
    "/terms",
  ];
  return paths.map((path) => ({
    url: `${ORIGIN}${path || "/"}`,
    changeFrequency: "weekly" as const,
    priority: path === "" ? 1 : 0.6,
  }));
}
