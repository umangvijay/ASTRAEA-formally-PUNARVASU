"""Playwright executor + screenshot-diff verifier + sandboxed browser context."""

from __future__ import annotations

import io
import os
import tempfile
from pathlib import Path

from PIL import Image
from playwright.async_api import async_playwright

from app.config import settings


def ensure_playwright_browsers() -> bool:
    """Cursor (and some CI) inject PLAYWRIGHT_BROWSERS_PATH pointing at an empty
    sandbox cache. If that path has no Chromium, use the real user/project cache
    so OPERATOR can actually launch a browser."""
    def has_chromium(root: Path) -> bool:
        if not root.is_dir():
            return False
        names = {"chrome-headless-shell", "chrome", "Chromium"}
        return any(p.is_file() and p.stat().st_size > 1_000_000 and p.name in names for p in root.rglob("*"))

    current = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if current and has_chromium(Path(current)):
        return True
    candidates = [
        Path.home() / "Library/Caches/ms-playwright",
        Path.home() / ".cache/ms-playwright",
        Path(__file__).resolve().parents[3] / ".playwright-browsers",
    ]
    for candidate in candidates:
        if has_chromium(candidate):
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(candidate)
            return True
    os.environ.pop("PLAYWRIGHT_BROWSERS_PATH", None)
    default_ok = any(has_chromium(p) for p in candidates)
    return default_ok

# Mirrors parser._JS_COLLECT's selector + filtering so an element id (its pushed
# index) maps back to the same DOM node. Scrolls that node — and every scrollable
# ancestor — into view, then returns its FRESH viewport rect. Window-level
# scrollTo could not reach elements inside inner overflow containers (bug #9).
_JS_FOCUS = """
(targetId) => {
  const sel = 'a[href], button, input, select, textarea, [role="button"], [role="link"], [role="searchbox"], [onclick]';
  const nodes = [...document.querySelectorAll(sel)];
  let i = 0;
  for (const el of nodes) {
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) continue;
    const style = getComputedStyle(el);
    if (style.visibility === "hidden" || style.display === "none") continue;
    if (i === targetId) {
      el.scrollIntoView({block: "center", inline: "center"});
      const rr = el.getBoundingClientRect();
      return {x: rr.x, y: rr.y, w: rr.width, h: rr.height};
    }
    i++;
    if (i >= 250) break;
  }
  return null;
}
"""


class BrowserSession:
    """One browser per task, fully isolated: dedicated profile dir, all permissions
    denied, no host profile access. Container-level isolation (gVisor) lands in Phase 7."""

    def __init__(self):
        self._pw = None
        self.browser = None
        self.context = None
        self.page = None
        self.profile_dir = tempfile.mkdtemp(prefix="pvu-browser-")

    async def start(self) -> None:
        ensure_playwright_browsers()
        self._pw = await async_playwright().start()
        self.context = await self._pw.chromium.launch_persistent_context(
            self.profile_dir,
            headless=True,
            viewport={"width": 1280, "height": 800},
            args=["--disable-gpu", "--disable-dev-shm-usage", "--force-color-profile=srgb"],
            permissions=[],  # no clipboard / geolocation / notifications
        )
        self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()

    async def close(self) -> None:
        for closer in (self.context, self.browser, self._pw):
            try:
                if closer:
                    await closer.close()
            except Exception:
                pass
        import shutil

        shutil.rmtree(self.profile_dir, ignore_errors=True)

    async def fresh_page(self) -> None:
        """One task = one page. Kills any navigation a previous task left in flight."""
        try:
            if self.page:
                await self.page.close()
        except Exception:
            pass
        self.page = await self.context.new_page()

    async def settle(self) -> None:
        try:
            await self.page.wait_for_load_state("load", timeout=8000)
        except Exception:
            pass
        await self.page.wait_for_timeout(250)

    async def goto(self, url: str) -> None:
        await self.page.goto(url, wait_until="load",
                             timeout=settings.operator_action_timeout_s * 1000)
        await self.settle()

    async def load_html(self, html: str) -> None:
        await self.page.set_content(html, wait_until="domcontentloaded")

    async def perform(self, action: dict, elements: list[dict]) -> dict:
        """Execute one decided action. Raises ValueError on impossible actions —
        the runner treats that as a failed step and replans."""
        kind = action["action"]
        el_id = action.get("element")
        el = next((e for e in elements if e["id"] == el_id), None)

        if kind in ("click", "type", "press") and el is None:
            raise ValueError(f"element {el_id} not on screen")

        if el is not None and kind in ("click", "type", "press", "select"):
            # Scroll the specific element (and any inner scroll container) into view,
            # then click its fresh viewport center — robust to overflow containers (bug #9).
            rect = None
            try:
                rect = await self.page.evaluate(_JS_FOCUS, el_id)
            except Exception:
                rect = None
            if rect is None:
                # fallback: window-level scroll using the parse-time absolute coords
                target_y = max(0, el["y"] - 300)
                scroll = await self.page.evaluate(
                    "y => { window.scrollTo(0, y); return [window.scrollX, window.scrollY]; }",
                    target_y)
                sx, sy = scroll[0], scroll[1]
                rect = {"x": el["x"] - sx, "y": el["y"] - sy, "w": el["w"], "h": el["h"]}
            if kind in ("click", "type", "select"):
                await self.page.mouse.click(rect["x"] + rect["w"] / 2,
                                            rect["y"] + rect["h"] / 2)

        if kind == "type":
            await self.page.keyboard.type(action.get("text", ""), delay=15)
        elif kind == "press":
            await self.page.keyboard.press(action.get("text", "Enter"))
        elif kind == "click":
            pass  # already executed in the shared scroll-into-view block above
        elif kind == "select":
            pass  # opened like a click above; the next pass grounds the expanded options
        elif kind == "scroll":
            await self.page.mouse.wheel(0, 600)
        elif kind in ("done", "fail"):
            return {"done": True}
        else:
            raise ValueError(f"unknown action '{kind}'")

        try:
            await self.page.wait_for_load_state("load", timeout=8000)
        except Exception:
            pass
        return {"done": False, "url": self.page.url, "title": await self.page.title()}


def pixel_diff_pct(a: bytes, b: bytes) -> float:
    """Fraction of changed pixels between two screenshots (verification signal)."""
    ia, ib = Image.open(io.BytesIO(a)).convert("L"), Image.open(io.BytesIO(b)).convert("L")
    if ia.size != ib.size:
        return 100.0
    wa, ha = ia.size
    pa, pb = ia.tobytes(), ib.tobytes()
    changed = sum(1 for x, y in zip(pa, pb) if abs(x - y) > 12)
    return round(100.0 * changed / (wa * ha), 3)


def snapshot_state(page) -> dict:
    return {"url": page.url, "title": None}
