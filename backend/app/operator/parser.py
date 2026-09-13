"""Screen grounding: parse the page into numbered, clickable elements + a Set-of-Mark image.

Backend `dom` (default): real bounding boxes from the live DOM/accessibility tree via
Playwright — fast, deterministic, works on any site with zero extra weights.
Backend `omniparser`: Microsoft OmniParser v2 (vision icon/text detection) — plugs into
the same interface when weights + GPU are available (ASTRAEA_OPERATOR_PARSER=omniparser).

The SoM image is the screenshot with every element boxed and numbered — exactly what the
VLM (or the heuristic planner) reasons over.
"""

from __future__ import annotations

import base64
import io

from PIL import Image, ImageDraw, ImageFont

_JS_COLLECT = """
() => {
  const sel = 'a[href], button, input, select, textarea, [role="button"], [role="link"], [role="searchbox"], [onclick]';
  const nodes = [...document.querySelectorAll(sel)];
  const out = [];
  let i = 0;
  for (const el of nodes) {
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) continue;
    const style = getComputedStyle(el);
    if (style.visibility === "hidden" || style.display === "none") continue;
    const text = (el.innerText || el.value || el.placeholder || el.getAttribute("aria-label") || el.alt || "").trim().slice(0, 80);
    out.push({
      id: i++,
      tag: el.tagName.toLowerCase(),
      role: el.getAttribute("role") || (el.tagName.toLowerCase() === "input" ? (el.type || "text") : el.tagName.toLowerCase()),
      text,
      placeholder: el.placeholder || "",
      name_attr: el.name || el.getAttribute("data-test") || el.id || "",
      href: el.href ? String(el.href).slice(0, 120) : "",
      x: Math.round(r.x + scrollX), y: Math.round(r.y + scrollY),
      w: Math.round(r.width), h: Math.round(r.height),
      view: (r.y >= 0 && r.bottom <= innerHeight),
    });
    if (out.length >= 250) break;
  }
  return out;
}
"""


async def parse_page(page) -> tuple[bytes, bytes, list[dict]]:
    """Returns (raw_screenshot, som_screenshot, elements). Screenshot retries absorb
    transient headless-chromium rasterizer failures."""
    import asyncio as _aio

    elements = None
    for attempt in range(3):
        try:
            elements = await page.evaluate(_JS_COLLECT)
            break
        except Exception:  # noqa: BLE001 — execution context dies mid-navigation
            if attempt == 2:
                raise
            try:
                await page.wait_for_load_state("load", timeout=5000)
            except Exception:
                pass
            await _aio.sleep(0.3)
    if elements is None:
        elements = []
    raw = None
    for attempt in range(4):
        try:
            raw = await page.screenshot(type="png")
            break
        except Exception:  # noqa: BLE001 — retry with backoff
            if attempt == 3:
                raise
            await _aio.sleep(0.4 * (attempt + 1))
    som = annotate(raw, elements)
    return raw, som, elements


def annotate(png: bytes, elements: list[dict]) -> bytes:
    img = Image.open(io.BytesIO(png)).convert("RGB")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 11)
    except Exception:
        font = ImageFont.load_default()
    for el in elements:
        if not el.get("view"):
            continue  # below/above the fold: not on this screenshot
        x, y, w, h = el["x"], el["y"], el["w"], el["h"]
        draw.rectangle([x, y, x + w, y + h], outline=(232, 93, 42), width=2)
        label = str(el["id"])
        bx, by = max(0, x - 1), max(0, y - 14)
        draw.rectangle([bx, by, bx + 10 + 6 * len(label), by + 14], fill=(20, 20, 20))
        draw.text((bx + 3, by + 1), label, fill=(250, 247, 242), font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def b64(png: bytes) -> str:
    return base64.b64encode(png).decode()
