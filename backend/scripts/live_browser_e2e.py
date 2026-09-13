"""Click through the live Blueprint console the way a person would."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.operator.executor import ensure_playwright_browsers  # noqa: E402

ensure_playwright_browsers()

from playwright.sync_api import sync_playwright  # noqa: E402

def _web() -> str:
    runtime = Path(__file__).resolve().parents[2] / "data" / "runtime.json"
    port = 3000
    if runtime.exists():
        port = json.loads(runtime.read_text()).get("frontend_port", 3000)
    return f"http://127.0.0.1:{port}"


WEB = _web()
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
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 900})

        page.goto(f"{WEB}/", wait_until="domcontentloaded")
        ok("landing wordmark", page.get_by_text("ASTRAEA", exact=False).first.is_visible())
        ok("cosmos earth photo is mounted",
           page.locator(".cosmos-earth").count() >= 1)
        ok("sun overlay is gone",
           page.locator("img.cosmos-sun, .cosmos-sun").count() == 0)
        ok("comets are in the sky",
           page.locator(".cosmos-comet").count() >= 1)
        ok("no mouse-following cursor ball",
           page.locator(".cursor-glow, #cursor-glow, .cursor-ball").count() == 0)

        page.goto(f"{WEB}/docs", wait_until="domcontentloaded")
        ok("docs overview has body",
           shown(page.get_by_text("Command dashboard", exact=False)))

        page.goto(f"{WEB}/docs/architecture", wait_until="domcontentloaded")
        ok("architecture heading", page.get_by_text("How Astraea is built", exact=False).first.is_visible())
        ok("architecture article is in the docs pane",
           shown(page.locator("#docs-content").get_by_text("CONTROL PLANE STACK", exact=False), 8000))
        box = page.get_by_role("heading", name="How Astraea is built.").bounding_box()
        ok("architecture heading is not a clipped hero title",
           bool(box) and box["height"] < 120,
           f"h1 height={box['height'] if box else None}")

        page.goto(f"{WEB}/login", wait_until="domcontentloaded")
        guest_btn = page.get_by_role("button", name="Or continue as guest")
        guest_btn.wait_for(state="visible", timeout=15000)
        page.wait_for_timeout(400)
        with page.expect_response(lambda r: "/api/auth/guest" in r.url, timeout=15000):
            guest_btn.click()
        page.wait_for_url("**/console", timeout=20000)
        ok("guest lands on console", "/console" in page.url)

        shown(page.get_by_text("Good day", exact=False), 10000)
        body = page.inner_text("body")
        ok("overview not fake-all-up", "API ERROR" not in body)
        chip = page.locator(".selftest-chip")
        try:
            chip.wait_for(state="visible", timeout=15000)
            page.wait_for_function(
                """() => {
                  const el = document.querySelector('.selftest-chip');
                  return el && el.textContent && !el.textContent.includes('…');
                }""",
                timeout=15000,
            )
            st = page.inner_text("body").lower()
            ok("selftest visible", "degraded" in st or "all systems ok" in st, chip.inner_text())
        except Exception as exc:
            ok("selftest visible", False, str(exc)[:180])

        page.goto(f"{WEB}/console/fusion", wait_until="domcontentloaded")
        ok("fusion title", shown(page.get_by_role("heading", name="Fusion.")))
        ok("fusion has start-job", shown(page.get_by_text("Start a job", exact=False)))

        page.goto(f"{WEB}/console/operator", wait_until="domcontentloaded")
        ok("operator research form", shown(page.get_by_text("LIVE WEB RESEARCH", exact=False)))
        page.get_by_placeholder("what is Astraea the constellation").fill(
            "what is the constellation Astraea"
        )
        page.get_by_role("button", name="Research").click()
        try:
            page.get_by_text("Fetching…").wait_for(state="hidden", timeout=45000)
        except Exception:
            pass
        shown(page.get_by_text("engine duckduckgo", exact=False), 15000)
        op = page.inner_text("body")
        ok("research returned a live URL",
           "wikipedia.org" in op.lower() or "theoi.com" in op.lower()
           or "engine duckduckgo" in op.lower() or "engine brave" in op.lower(),
           op[400:800])
        ok("research fold is not a false sentinel block",
           "blocked by sentinel" not in op.lower(),
           op[400:700])

        page.goto(f"{WEB}/console/studio", wait_until="domcontentloaded")
        ok("studio is honest (Chat + Fusion)",
           shown(page.get_by_text("Studio is Chat", exact=False))
           or shown(page.get_by_text("NOT A SEPARATE PRODUCT", exact=False)),
           page.inner_text("body")[:240])

        page.goto(f"{WEB}/console/medic", wait_until="domcontentloaded")
        ok("medic page", shown(page.get_by_role("heading", name="MEDIC."), 20000))

        page.goto(f"{WEB}/console/chat", wait_until="domcontentloaded")
        ok("chat page", shown(page.get_by_role("heading", name="Talk to the plane."), 15000))

        page.goto(f"{WEB}/console/sentinel", wait_until="domcontentloaded")
        ok("sentinel page", shown(page.get_by_role("heading", name="Sentinel."), 20000))

        page.goto(f"{WEB}/privacy", wait_until="domcontentloaded")
        priv = page.inner_text("body")
        ok("privacy says Argon2id", "Argon2id" in priv or "argon2id" in priv.lower(), priv[:200])

        browser.close()

    print(f"\n{len(fails)} browser check(s) failed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
