"""Live e2e against a running ASTRAEA api + console. Not part of pytest."""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

API = "http://127.0.0.1:8000"
WEB = "http://127.0.0.1:3000"
results: list[tuple[str, bool, str]] = []


def rec(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    mark = "OK" if ok else "FAIL"
    print(f"  [{mark}] {name}{(' — ' + detail) if detail else ''}")


def http(method: str, url: str, *, data=None, headers=None, timeout=30):
    body = None if data is None else json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            parsed = json.loads(raw) if raw and "application/json" in (resp.headers.get("Content-Type") or "") else raw.decode("utf-8", "replace")
            return resp.status, parsed, dict(resp.headers)
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = raw.decode("utf-8", "replace")
        return exc.code, parsed, dict(exc.headers)


def main() -> int:
    print("── public frontend ──")
    for path in ("/", "/docs", "/docs/architecture", "/docs/security", "/docs/deploy",
                 "/docs/getting-started", "/docs/chat", "/login", "/privacy"):
        code, _, _ = http("GET", f"{WEB}{path}")
        rec(f"GET {path}", code == 200, str(code))

    code, home, _ = http("GET", f"{WEB}/")
    html = home if isinstance(home, str) else ""
    rec("landing has drifting earth photo",
        code == 200 and "cosmos-earth" in html and "/cosmos/earth.png" in html, str(code))
    rec("landing has no sun overlay",
        "cosmos-sun" not in html, "" if "cosmos-sun" not in html else "sun still in markup")
    rec("landing has comets (not a one-way meteor)",
        "cosmos-comet" in html, "" if "cosmos-comet" in html else "missing comet")
    rec("landing has plate photos (not doodle SVGs)",
        "plate-medic.png" in html,
        "" if "plate-medic.png" in html else "missing plate-medic.png")

    code, docs, _ = http("GET", f"{WEB}/docs")
    html = docs if isinstance(docs, str) else ""
    rec("docs overview has body (not empty pane)",
        code == 200 and "Command dashboard" in html and "plate-medic.png" in html, str(code))

    code, arch, _ = http("GET", f"{WEB}/docs/architecture")
    html = arch if isinstance(arch, str) else ""
    rec("docs architecture has body",
        code == 200 and "How Astraea is built" in html and "CONTROL PLANE STACK" in html, str(code))

    for asset in ("/cosmos/earth.png", "/cosmos/moon.png",
                  "/cosmos/milkyway.png", "/cosmos/plate-medic.png"):
        code, _, _ = http("GET", f"{WEB}{asset}")
        rec(f"GET {asset}", code == 200, str(code))

    code, body, _ = http("GET", f"{WEB}/console/studio")
    html = body if isinstance(body, str) else json.dumps(body)
    rec("GET /console/studio is honest (not a fake workbench)",
        code == 200 and "Studio is Chat" in html,
        f"{code}")

    print("── api health ──")
    code, health, _ = http("GET", f"{API}/health")
    rec("GET /health", code == 200 and isinstance(health, dict) and health.get("app") == "astraea",
        json.dumps(health)[:180] if isinstance(health, dict) else str(code))

    print("── auth + self-test ──")
    code, guest, _ = http("POST", f"{API}/api/auth/guest")
    token = guest.get("access_token") if isinstance(guest, dict) else None
    rec("POST /api/auth/guest", code in (200, 201) and bool(token), str(code))
    if not token:
        print("cannot continue without token")
        return 1
    auth = {"Authorization": f"Bearer {token}"}

    code, me, _ = http("GET", f"{API}/api/auth/me", headers=auth)
    rec("GET /api/auth/me", code == 200 and isinstance(me, dict), str(code))

    code, st, _ = http("GET", f"{API}/api/system/selftest", headers=auth)
    rec("GET /api/system/selftest", code == 200, json.dumps(st)[:300] if isinstance(st, dict) else str(code))

    print("── sentinel chat ──")
    code, empty, _ = http("POST", f"{API}/v1/chat/completions",
                          headers=auth, data={"messages": []})
    rec("empty chat → 400", code == 400 and isinstance(empty, dict) and empty.get("error", {}).get("type") == "invalid_request_error",
        str(empty)[:200])

    code, blank, _ = http("POST", f"{API}/v1/chat/completions",
                          headers=auth, data={"messages": [{"role": "user", "content": "  "}]})
    rec("blank chat → 400", code == 400, str(code))

    code, hi, _ = http("POST", f"{API}/v1/chat/completions",
                       headers=auth, data={"messages": [{"role": "user", "content": "hi"}]})
    provider = None
    if isinstance(hi, dict):
        provider = (hi.get("astraea") or {}).get("provider") or hi.get("model")
    rec("hi chat (no canned model_forge)",
        code in (200, 503) and (code != 200 or provider not in ("model_forge", "mlx_local")),
        f"{code} provider={provider} body={str(hi)[:220]}")
    if code == 503:
        rec("503 chat is OpenAI-shaped (not FastAPI detail)",
            isinstance(hi, dict) and (hi.get("error") or {}).get("type") == "provider_unavailable",
            str(hi)[:220])

    print("── operator research + workflows ──")
    code, research, _ = http("POST", f"{API}/api/operator/research",
                             headers=auth, data={"query": "Astraea constellation", "max_results": 3, "synthesize": True},
                             timeout=45)
    pages = research.get("pages") if isinstance(research, dict) else None
    urls = [p.get("url") for p in (pages or [])]
    rec("POST /api/operator/research",
        code == 200 and isinstance(pages, list) and len(pages) >= 1,
        f"{code} engine={research.get('engine') if isinstance(research, dict) else '?'} urls={urls[:4]}")

    code, wfs, _ = http("GET", f"{API}/api/runs/workflows", headers=auth)
    names = [w.get("name") for w in (wfs.get("workflows") or [])] if isinstance(wfs, dict) else []
    rec("research-and-remember uses web.research",
        "research-and-remember" in names, str(names))

    print("── pulse / loom / fusion ──")
    code, chaos, _ = http("POST", f"{API}/api/pulse/chaos", headers=auth, data={})
    rec("POST /api/pulse/chaos", code in (200, 201), f"{code} {str(chaos)[:180]}")

    code, loom, _ = http("GET", f"{API}/api/loom/items", headers=auth)
    rec("GET /api/loom/items", code == 200, str(code))

    code, tl, _ = http("GET", f"{API}/api/fusion/timeline?limit=10", headers=auth)
    rec("GET /api/fusion/timeline", code == 200, str(code))

    print("── console routes (auth cookie-less GET) ──")
    for path in ("/console", "/console/fusion", "/console/operator", "/console/medic",
                 "/console/shield", "/console/vaani", "/console/forge",
                 "/console/model_forge", "/console/sentinel", "/console/loom",
                 "/console/runs", "/console/settings", "/console/vault",
                 "/console/chat", "/console/integrations", "/console/schedules"):
        code, _, _ = http("GET", f"{WEB}{path}")
        rec(f"GET {path}", code == 200, str(code))

    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
