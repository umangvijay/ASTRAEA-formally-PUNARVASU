import { NextResponse } from "next/server";
import { readFile } from "fs/promises";
import path from "path";

export const dynamic = "force-dynamic";

export async function GET() {
  let file: { api_port?: number; frontend_port?: number; api_public_url?: string } = {};
  try {
    // repo root is three levels up from frontend/app/api/runtime-config
    const p = path.resolve(process.cwd(), "..", "data", "runtime.json");
    const raw = await readFile(p, "utf8");
    file = JSON.parse(raw);
  } catch {
    file = { api_port: 8000, frontend_port: 3000 };
  }
  const envUrl = process.env.ASTRAEA_PUBLIC_API_URL || process.env.ASTRAEA_API_PUBLIC_URL || "";
  const onCloud = Boolean(process.env.K_SERVICE) || process.env.ASTRAEA_USE_API_PROXY === "1";
  return NextResponse.json({
    api_port: file.api_port ?? 8000,
    frontend_port: file.frontend_port ?? 3000,
    // Browser on Cloud Run talks same-origin /api/astraea (this process proxies).
    // Direct api_public_url is only for laptop / split-origin deploys.
    use_proxy: onCloud,
    api_public_url: onCloud ? "" : (envUrl || file.api_public_url || ""),
    // WebSockets cannot ride the Next.js HTTP proxy — VAANI talks to the API origin.
    api_ws_url: envUrl || file.api_public_url || "",
  });
}
