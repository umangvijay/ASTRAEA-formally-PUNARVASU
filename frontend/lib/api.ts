// Shared client library: API access + the module registry (mirrors backend/app/modules.py).

// API base is discovered at runtime: the launcher shifts ports when they collide,
// so the console asks its own server for the resolved backend port (data/runtime.json).
let _resolvedBase: string | null = null;

export function setApiBase(base: string): void {
  _resolvedBase = base;
}

export async function resolveApiBase(): Promise<string> {
  if (_resolvedBase) return _resolvedBase;
  const host = typeof window !== "undefined" ? window.location.hostname : "localhost";
  try {
    const r = await fetch("/api/runtime-config", { cache: "no-store" });
    const cfg = await r.json();
    if (typeof cfg.api_public_url === "string" && cfg.api_public_url) {
      _resolvedBase = String(cfg.api_public_url).replace(/\/$/, "");
    } else {
      _resolvedBase = `http://${host}:${cfg.api_port ?? 8000}`;
    }
  } catch {
    _resolvedBase = `http://${host}:8000`;
  }
  return _resolvedBase;
}

export const API_BASE = "http://localhost:8000"; // fallback; real base resolved per call

export type ModuleMeta = {
  codename: string;
  name: string;
  title: string;
  profile: string;
  phase: number;
  blurb: string;
  benchmark: string;
  status?: string;
};

export type CoreServiceMeta = {
  codename: string;
  name: string;
  phase: number;
  blurb: string;
  status?: string;
};

export const MODULES: ModuleMeta[] = [
  {
    codename: "medic",
    name: "MEDIC",
    title: "AI SRE — the on-call engineer",
    profile: "sre",
    phase: 2,
    blurb:
      "Watches live telemetry, detects anomalies, correlates with deploys, reproduces the fault in a sandbox and opens the fix PR for your approval.",
    benchmark: "MTTD / MTTR on injected faults",
  },
  {
    codename: "operator",
    name: "OPERATOR",
    title: "Vision computer-use + live web",
    profile: "operator",
    phase: 3,
    blurb:
      "Searches, fetches and reads real public pages (DuckDuckGo / Brave), then operates screens where no API exists — vision-guided clicking with screenshot verification.",
    benchmark: "Success rate on a 20-task web suite",
  },
  {
    codename: "shield",
    name: "SHIELD",
    title: "AI SOC analyst",
    profile: "soc",
    phase: 4,
    blurb:
      "Defensive cyber agent: streams security events, correlates attacks into narratives, maps MITRE ATT&CK, graphs the intrusion and drafts containment for approval.",
    benchmark: "Detection rate / false-positive rate",
  },
  {
    codename: "vaani",
    name: "VAANI",
    title: "Voice AI employee",
    profile: "voice",
    phase: 5,
    blurb:
      "Full-duplex voice agent that answers calls and completes the work — books, follows up, hands over to humans. Sub-1.5s end-to-end, barge-in included.",
    benchmark: "p95 latency + task completion",
  },
  {
    codename: "forge",
    name: "FORGE",
    title: "Self-evolving engine",
    profile: "forge",
    phase: 6,
    blurb:
      "Turns agent failures into new skills: proposes tools and prompt patches, validates them in a sandbox, promotes only measured wins.",
    benchmark: "Week-over-week eval score",
  },
  {
    codename: "model_forge",
    name: "MODEL-FORGE",
    title: "Our own model",
    profile: "core",
    phase: 6,
    blurb:
      "A domain-expert model post-trained by us (SFT + GRPO on verifiable rewards) and served behind SENTINEL — our proprietary edge.",
    benchmark: "Held-out SQL test pass rate vs base model",
  },
];

export const CORE_SERVICES: CoreServiceMeta[] = [
  {
    codename: "sentinel",
    name: "SENTINEL",
    phase: 1,
    blurb:
      "LLM security firewall — every model call in the platform passes through it. Injection, jailbreak and Indic-PII detection; streaming output scanning.",
  },
  {
    codename: "loom",
    name: "LOOM",
    phase: 1,
    blurb:
      "The shared context fabric: your data, learned once, provenance-stamped, available to every module you switch on — never re-entered.",
  },
  {
    codename: "pulse",
    name: "PULSE",
    phase: 2,
    blurb:
      "Real-time telemetry bus: logs, metrics, traces and security events in one queryable stream feeding MEDIC and SHIELD alike.",
  },
];

// ── token / auth helpers ──────────────────────────────────────────
const TOKEN_KEY = "astraea_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  window.localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

// FastAPI 422 returns detail as an array of {loc, msg, ...} — make it human-readable
function detailToMessage(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => {
        if (d && typeof d === "object") {
          const loc = Array.isArray(d.loc) ? d.loc.filter((p: unknown) => p !== "body").join(".") : "";
          const msg = typeof d.msg === "string" ? d.msg.replace(/^value error,\s*/i, "") : String(d);
          return loc ? `${loc}: ${msg}` : msg;
        }
        return String(d);
      })
      .join("; ");
  }
  if (detail && typeof detail === "object" && "msg" in (detail as Record<string, unknown>)) {
    return String((detail as Record<string, unknown>).msg);
  }
  return fallback;
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init?.headers as Record<string, string> | undefined),
  };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const base = await resolveApiBase();
  const resp = await fetch(`${base}${path}`, { ...init, headers });
  if (resp.status === 401 && typeof window !== "undefined") {
    clearToken();
    window.location.href = "/login";
    throw new ApiError(401, "session expired");
  }
  const body = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    const b = body as { detail?: unknown; error?: { message?: string } };
    const fromError = typeof b.error?.message === "string" ? b.error.message : "";
    throw new ApiError(resp.status, fromError || detailToMessage(b.detail, resp.statusText));
  }
  return body as T;
}

// ── realtime SSE (fetch-based so the Authorization header works) ─────────
export function streamSSE(
  path: string,
  onEvent: (data: Record<string, unknown>) => void
): () => void {
  const controller = new AbortController();
  (async () => {
    try {
      const base = await resolveApiBase();
      const resp = await fetch(`${base}${path}`, {
        headers: { Authorization: `Bearer ${getToken() ?? ""}` },
        signal: controller.signal,
      });
      if (!resp.ok || !resp.body) return;
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        let idx;
        while ((idx = buf.indexOf("\n\n")) >= 0) {
          const frame = buf.slice(0, idx);
          buf = buf.slice(idx + 2);
          for (const line of frame.split("\n")) {
            if (line.startsWith("data: ")) {
              const data = line.slice(6);
              if (data === "[DONE]") return;
              try {
                onEvent(JSON.parse(data));
              } catch {
                /* keepalives and non-JSON frames are ignored */
              }
            }
          }
        }
      }
    } catch {
      /* aborted or network gone */
    }
  })();
  return () => controller.abort();
}
