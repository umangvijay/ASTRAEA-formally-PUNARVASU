"""Paint earth / moon / sun / milky-way plates into public/cosmos (no CDN)."""
from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

OUT = Path(__file__).resolve().parents[1] / "public" / "cosmos"
OUT.mkdir(parents=True, exist_ok=True)
RNG = random.Random(13)


def sphere_shade(size: int, color_fn, rim):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    px = img.load()
    r = size / 2
    cx = cy = r - 0.5
    for y in range(size):
        for x in range(size):
            dx, dy = (x - cx) / r, (y - cy) / r
            d2 = dx * dx + dy * dy
            if d2 > 1:
                continue
            z = math.sqrt(max(0.0, 1 - d2))
            light = max(0.0, dx * -0.45 + dy * -0.25 + z * 0.85)
            col = color_fn(dx, dy, z, light)
            edge = max(0.0, 1 - (math.sqrt(d2) ** 8))
            a = int(255 * edge)
            px[x, y] = (col[0], col[1], col[2], a)
    if rim:
        glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        g = ImageDraw.Draw(glow)
        g.ellipse((2, 2, size - 3, size - 3), outline=rim + (90,))
        img = Image.alpha_composite(glow, img)
    return img


def earth_color(dx, dy, z, light):
    lat = dy
    lon = math.atan2(dx, z)
    land = math.sin(lon * 3.2 + lat * 2.1) + math.sin(lat * 5.4) * 0.55
    cloud = math.sin(lon * 7 + lat * 3) * math.sin(lat * 4 + 1.2)
    if land > 0.35:
        base = (46, 110, 58)
    elif land > 0.12:
        base = (194, 178, 128)
    else:
        base = (28, 72, 148)
    if cloud > 0.55:
        base = (230, 236, 242)
    shade = 0.28 + 0.72 * light
    return tuple(min(255, int(c * shade)) for c in base)


def moon_color(dx, dy, z, light):
    crater = math.sin(dx * 11 + dy * 9) * math.sin(dx * 6 - dy * 8)
    gray = 168 + int(crater * 28)
    if (dx + 0.25) ** 2 + (dy + 0.1) ** 2 < 0.04:
        gray -= 40
    if (dx - 0.35) ** 2 + (dy - 0.3) ** 2 < 0.02:
        gray -= 28
    shade = 0.22 + 0.78 * light
    v = min(255, max(40, int(gray * shade)))
    return (v, v, int(v * 0.96))


def sun(size=280):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx = cy = size // 2
    for i in range(size // 2, 0, -1):
        t = 1 - i / (size / 2)
        a = int(18 + 140 * (1 - t) ** 2)
        col = (255, int(150 + 80 * t), int(40 + 30 * t), a)
        draw.ellipse((cx - i, cy - i, cx + i, cy + i), fill=col)
    core = size // 7
    draw.ellipse((cx - core, cy - core, cx + core, cy + core), fill=(255, 236, 180, 255))
    return img.filter(ImageFilter.GaussianBlur(1.2))


def milkyway(w=1600, h=900):
    img = Image.new("RGB", (w, h), (250, 247, 242))
    px = img.load()
    for _ in range(1800):
        x, y = RNG.randint(0, w - 1), RNG.randint(0, h - 1)
        ink = RNG.choice([(20, 20, 20), (232, 93, 42), (20, 20, 20)])
        a = RNG.random()
        if a < 0.7:
            px[x, y] = tuple(int(250 * (1 - a * 0.35) + c * a * 0.35) for c in ink)
        else:
            for ox, oy in ((0, 0), (1, 0), (0, 1)):
                if 0 <= x + ox < w and 0 <= y + oy < h:
                    px[x + ox, y + oy] = (232, 93, 42) if RNG.random() > 0.85 else (30, 30, 30)
    # faint galactic band
    band = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(band)
    d.polygon([(0, int(h * 0.38)), (w, int(h * 0.22)), (w, int(h * 0.48)), (0, int(h * 0.62))],
              fill=(20, 20, 20, 18))
    img = Image.alpha_composite(img.convert("RGBA"), band).convert("RGB")
    return img


def main() -> None:
    sphere_shade(512, earth_color, (90, 170, 230)).save(OUT / "earth.png")
    sphere_shade(256, moon_color, (200, 200, 196)).save(OUT / "moon.png")
    sun().save(OUT / "sun.png")
    milkyway().save(OUT / "milkyway.png", quality=86)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
