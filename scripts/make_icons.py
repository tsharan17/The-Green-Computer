"""Draw the app icons (the logo mark from frontend/src/components/Logo.tsx) into frontend/public.

    python scripts/make_icons.py

Writes icon-192.png, icon-512.png, icon-maskable-512.png, apple-touch-icon.png and favicon.svg.
Needs Pillow (in the backend's dev environment). Run again only if the mark changes.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parents[1] / "frontend" / "public"
ACCENT, INK = "#4cbb17", "#0b2205"
SS = 4  # supersampling, for smooth edges after the downscale


def _bezier(p0, p1, p2, p3, n=24):
    return [tuple((1 - t) ** 3 * a + 3 * (1 - t) ** 2 * t * b + 3 * (1 - t) * t**2 * c + t**3 * d
                  for a, b, c, d in zip(p0, p1, p2, p3, strict=True))
            for t in (i / n for i in range(n + 1))]  # fmt: skip


def mark(size: int, *, maskable: bool = False) -> Image.Image:
    """The mark on the 32-unit grid of Logo.tsx. Maskable icons fill the square and keep the mark
    inside the central 80% safe zone, since launchers crop them to their own shape."""
    px = size * SS
    img = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if maskable:
        d.rectangle([0, 0, px, px], fill=ACCENT)
        scale, off = px * 0.8 / 32, px * 0.1
    else:
        scale, off = px / 32, 0.0
        d.rounded_rectangle([1 * scale, 1 * scale, 31 * scale, 31 * scale], radius=7 * scale, fill=ACCENT)

    def xy(x: float, y: float) -> tuple[float, float]:
        return off + x * scale, off + y * scale

    w = max(1, round(1.6 * scale))
    for a in (11, 16, 21):  # the pins
        for (x0, y0), (x1, y1) in (((a, 6), (a, 9)), ((a, 23), (a, 26)), ((6, a), (9, a)), ((23, a), (26, a))):
            d.line([xy(x0, y0), xy(x1, y1)], fill=INK, width=w)
            for x, y in ((x0, y0), (x1, y1)):  # round caps
                cx, cy = xy(x, y)
                d.ellipse([cx - w / 2, cy - w / 2, cx + w / 2, cy + w / 2], fill=INK)
    d.rounded_rectangle([*xy(9, 9), *xy(23, 23)], radius=2.5 * scale, outline=INK, width=w)
    leaf = _bezier((12, 20), (12, 15), (15, 12), (20, 12)) + _bezier((20, 12), (20, 17), (17, 20), (12, 20))
    d.polygon([xy(x, y) for x, y in leaf], fill=INK)
    return img.resize((size, size), Image.Resampling.LANCZOS)


SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
    f'<rect x="1" y="1" width="30" height="30" rx="7" fill="{ACCENT}"/>'
    f'<g stroke="{INK}" stroke-width="1.6" stroke-linecap="round" fill="none">'
    '<path d="M11 6v3M16 6v3M21 6v3M11 23v3M16 23v3M21 23v3M6 11h3M6 16h3M6 21h3M23 11h3M23 16h3M23 21h3"/>'
    '<rect x="9" y="9" width="14" height="14" rx="2.5"/></g>'
    f'<path d="M12 20c0-5 3-8 8-8 0 5-3 8-8 8z" fill="{INK}"/></svg>\n'
)

if __name__ == "__main__":
    mark(192).save(OUT / "icon-192.png", optimize=True)
    mark(512).save(OUT / "icon-512.png", optimize=True)
    mark(512, maskable=True).save(OUT / "icon-maskable-512.png", optimize=True)
    # iOS draws its own rounded corners and shows transparency as black: use the full-bleed version
    mark(180, maskable=True).convert("RGB").save(OUT / "apple-touch-icon.png", optimize=True)
    (OUT / "favicon.svg").write_text(SVG, encoding="utf-8", newline="\n")
    print("icons written to", OUT)
