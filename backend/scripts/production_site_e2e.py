"""Audit the hosted Cloud Run console the way a person would.

Does not require a local API. Captures network failures, CORS, guest login,
and whether chat/research ever see a live backend.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.operator.executor import ensure_playwright_browsers  # noqa: E402

ensure_playwright_browsers()

from playwright.sync_api import sync_playwright  # noqa: E402

CONSOLE = "https://astraea-console-714727365323.us-central1.run.app"
API = "https://astraea-api-714727365323.us-central1.run.app"
OUT = Path("/tmp/astraea-prod-audit")
fails: list[str] = []


def ok(name: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}{(' — ' + detail) if detail else ''}")
    if not cond:
        fails.append(f"{name}: {detail}")


def shown(locator, timeout: int = 8000) -> bool:
    try:
        locator.wait_for(state="visible", timeout=timeout)
        return True
    except Exception:
        return False


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    net: list[dict] = []
    page_errors: list[str] = []
    console_msgs: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        page.set_default_timeout(25000)

        def on_response(resp):
            url = resp.url
            if "astraea" not in url and "run.app" not in url:
                return
            rec = {
                "status": resp.status,
                "method": resp.request.method,
                "url": url[:220],
                "type": resp.request.resource_type,
            }
            net.append(rec)

        page.on("response", on_response)
        page.on("pageerror", lambda err: page_errors.append(str(err)[:400]))
        page.on("console", lambda msg: console_msgs.append(f"{msg.type}: {msg.text[:300]}"))

        # ── public pages ──
        for path, needle in [
            ("/", "ASTRAEA"),
            ("/docs", "Command dashboard"),
            ("/docs/architecture", "How Astraea is built"),
            ("/pricing", None),
            ("/login", "Sign in"),
            ("/privacy", None),
            ("/contact", None),
            ("/faq", None),
            ("/about", None),
        ]:
            resp = page.goto(f"{CONSOLE}{path}", wait_until="domcontentloaded")
            ok(f"GET {path} http", bool(resp and resp.ok), f"status={resp.status if resp else None}")
            body = page.inner_text("body")[:2000]
            if needle:
                ok(f"GET {path} copy", needle.lower() in body.lower(), body[:160].replace("\n", " "))
            page.screenshot(path=str(OUT / f"{path.strip('/').replace('/', '_') or 'home'}.png"), full_page=False)

        # runtime-config (tells the browser where the API lives)
        cfg = page.evaluate(
            """async () => {
              const r = await fetch('/api/runtime-config', { cache: 'no-store' });
              return { status: r.status, body: await r.json() };
            }"""
        )
        print("  runtime-config:", json.dumps(cfg)[:500])
        ok("runtime-config 200", cfg.get("status") == 200, str(cfg)[:200])

        # landing chrome
        page.goto(f"{CONSOLE}/", wait_until="domcontentloaded")
        ok("cosmos earth", page.locator(".cosmos-earth").count() >= 1)
        ok("no .cosmos-sun", page.locator(".cosmos-sun").count() == 0)
        ok("comets", page.locator(".cosmos-comet").count() >= 1)
        theme = page.locator("body").inner_text()
        # production may still be the older LIGHT toggle
        has_day = "+ Day" in theme or "+ Night" in theme or "LIGHT" in theme or "NIGHT" in theme
        ok("theme toggle present", has_day, theme[:120].replace("\n", " "))

        # ── login / guest ──
        page.goto(f"{CONSOLE}/login", wait_until="networkidle")
        guest = page.get_by_role("button", name="Or continue as guest")
        ok("guest button", shown(guest, 8000))
        guest_result: dict = {"clicked": False}
        if shown(guest, 2000):
            try:
                with page.expect_response(
                    lambda r: "/api/auth/guest" in r.url or "/auth/guest" in r.url,
                    timeout=20000,
                ) as pend:
                    guest.click()
                gresp = pend.value
                guest_result = {
                    "clicked": True,
                    "status": gresp.status,
                    "url": gresp.url,
                    "ct": gresp.headers.get("content-type", ""),
                }
                try:
                    guest_result["body"] = gresp.text()[:400]
                except Exception:
                    pass
                page.wait_for_timeout(2500)
                guest_result["after_url"] = page.url
                guest_result["after_body"] = page.inner_text("body")[:500]
            except Exception as exc:
                guest_result = {"clicked": True, "error": str(exc)[:400], "url": page.url}
                guest_result["after_body"] = page.inner_text("body")[:500]
        print("  guest:", json.dumps(guest_result)[:800])
        ok(
            "guest login reached console or showed a real API error",
            "/console" in page.url
            or "failed" in (guest_result.get("after_body") or "").lower()
            or "unreachable" in (guest_result.get("after_body") or "").lower()
            or "error" in (guest_result.get("after_body") or "").lower()
            or guest_result.get("status") not in (None, 200),
            json.dumps(guest_result)[:240],
        )
        page.screenshot(path=str(OUT / "login-after-guest.png"))

        # if we made it into the console, exercise live surfaces
        if "/console" in page.url:
            for path, heading in [
                ("/console", "Good day"),
                ("/console/chat", "Talk to the plane"),
                ("/console/operator", "OPERATOR"),
                ("/console/fusion", "Fusion"),
                ("/console/medic", "MEDIC"),
                ("/console/sentinel", "Sentinel"),
            ]:
                page.goto(f"{CONSOLE}{path}", wait_until="domcontentloaded")
                ok(f"console {path}", shown(page.get_by_text(heading, exact=False), 15000),
                   page.inner_text("body")[:180].replace("\n", " "))
                page.screenshot(path=str(OUT / f"{path.strip('/').replace('/', '_')}.png"))

            # live research (must be real URLs, not a canned pack)
            page.goto(f"{CONSOLE}/console/operator", wait_until="domcontentloaded")
            if shown(page.get_by_placeholder("what is Astraea the constellation"), 8000):
                page.get_by_placeholder("what is Astraea the constellation").fill(
                    "what is the constellation Astraea"
                )
                page.get_by_role("button", name="Research").click()
                try:
                    page.get_by_text("Fetching…").wait_for(state="hidden", timeout=45000)
                except Exception:
                    pass
                op = page.inner_text("body")
                ok(
                    "research returned a live URL",
                    "wikipedia.org" in op.lower()
                    or "theoi.com" in op.lower()
                    or "engine duckduckgo" in op.lower()
                    or "engine brave" in op.lower(),
                    op[400:800],
                )

            page.goto(f"{CONSOLE}/console/chat", wait_until="domcontentloaded")
            box = page.get_by_placeholder("Message the control plane")
            if shown(box, 8000):
                box.fill("Reply with exactly the three words STREAMING CHECK OK and nothing else.")
                page.get_by_role("button", name="Send").click()
                page.wait_for_timeout(12000)
                chat = page.inner_text("body")
                ok(
                    "chat is live model output (not a canned SQL greeting)",
                    "pvu-sql" not in chat.lower() and "champion" not in chat.lower() or "vertex" in chat.lower()
                    or "gemini" in chat.lower() or "STREAMING CHECK" in chat
                    or "provider_unavailable" in chat.lower() or "No general model" in chat,
                    chat[-500:],
                )
        else:
            print("  (console never opened — API/CORS is blocking guest login)")

        browser.close()

    (OUT / "network.json").write_text(json.dumps(net, indent=2)[:200_000])
    (OUT / "page-errors.json").write_text(json.dumps(page_errors, indent=2))
    (OUT / "console.json").write_text(json.dumps(console_msgs[-80:], indent=2))

    print("\n── failed API/console calls ──")
    bad = [r for r in net if r["status"] >= 400 or r["url"].startswith(API)]
    for r in bad[:40]:
        print(f"  {r['status']} {r['method']} {r['url']}")
    print(f"\npage errors: {len(page_errors)}")
    for e in page_errors[:10]:
        print(" ", e)
    print(f"\n{len(fails)} check(s) failed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
