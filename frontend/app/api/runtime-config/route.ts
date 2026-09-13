import { NextResponse } from "next/server";
import { readFile } from "fs/promises";
import path from "path";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    // repo root is three levels up from frontend/app/api/runtime-config
    const p = path.resolve(process.cwd(), "..", "data", "runtime.json");
    const raw = await readFile(p, "utf8");
    return NextResponse.json(JSON.parse(raw));
  } catch {
    return NextResponse.json({ api_port: 8000, frontend_port: 3000 });
  }
}
