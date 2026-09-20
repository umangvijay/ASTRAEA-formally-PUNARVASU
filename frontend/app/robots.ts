import type { MetadataRoute } from "next";

const ORIGIN =
  process.env.ASTRAEA_PUBLIC_CONSOLE_URL
  || process.env.NEXT_PUBLIC_SITE_URL
  || "https://astraea-console-714727365323.us-central1.run.app";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: { userAgent: "*", allow: "/" },
    sitemap: `${ORIGIN}/sitemap.xml`,
  };
}
