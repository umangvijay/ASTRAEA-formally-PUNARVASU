import { NextRequest, NextResponse } from "next/server";
import { readFile } from "fs/promises";
import path from "path";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 300;

const HOP = new Set(["host", "connection", "content-length", "transfer-encoding", "content-encoding"]);

async function apiOrigin(): Promise<string> {
  const env = process.env.ASTRAEA_PUBLIC_API_URL || process.env.ASTRAEA_API_PUBLIC_URL || "";
  if (env) return env.replace(/\/$/, "");
  try {
    const p = path.resolve(process.cwd(), "..", "data", "runtime.json");
    const raw = await readFile(p, "utf8");
    const cfg = JSON.parse(raw) as { api_public_url?: string };
    if (cfg.api_public_url) return String(cfg.api_public_url).replace(/\/$/, "");
  } catch {
    /* no runtime.json on Cloud Run unless mounted */
  }
  return "";
}

async function proxy(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const base = await apiOrigin();
  if (!base) {
    return NextResponse.json(
      { detail: "API origin is not configured. Set ASTRAEA_PUBLIC_API_URL on the console service." },
      { status: 503 },
    );
  }
  const { path: segs } = await ctx.params;
  const dest = `${base}/${(segs || []).join("/")}${req.nextUrl.search}`;
  const headers = new Headers();
  req.headers.forEach((value, key) => {
    if (!HOP.has(key.toLowerCase())) headers.set(key, value);
  });
  const method = req.method.toUpperCase();
  const body = method === "GET" || method === "HEAD" ? undefined : await req.arrayBuffer();
  try {
    const resp = await fetch(dest, {
      method,
      headers,
      body,
      redirect: "manual",
      cache: "no-store",
    });
    const out = new Headers();
    resp.headers.forEach((value, key) => {
      if (!HOP.has(key.toLowerCase())) out.set(key, value);
    });
    return new NextResponse(resp.body, { status: resp.status, headers: out });
  } catch (err) {
    return NextResponse.json(
      {
        detail: `API unreachable at ${base}: ${err instanceof Error ? err.message : "fetch failed"}`,
      },
      { status: 502 },
    );
  }
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
export const OPTIONS = proxy;
export const HEAD = proxy;
