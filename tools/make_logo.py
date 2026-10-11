"""Draws the app logo: assets/logo.png (1024 px) and assets/app.ico (16–256 px).

Run: python tools/make_logo.py
Small icon sizes use a simplified drawing (thicker ring, no nozzle) so they stay readable.
"""

import math
from pathlib import Path

from PIL import Image, ImageDraw

ASSETS = Path(__file__).resolve().parent.parent / "assets"
GREEN = (0, 174, 66, 255)
TRACK = (40, 46, 60, 255)
WHITE = (236, 239, 244, 255)


def background(size: int) -> Image.Image:
    # Vertical gradient #181c26 -> #0c0e14 inside an iOS-like rounded square.
    grad = Image.new("RGBA", (1, 256))
    for y in range(256):
        t = y / 255
        grad.putpixel((0, y), (int(24 - 12 * t), int(28 - 14 * t), int(38 - 18 * t), 255))
    im = grad.resize((size, size), Image.BICUBIC)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1), radius=int(size * 0.235), fill=255)
    im.putalpha(mask)
    return im


def draw(size: int, simple: bool = False) -> Image.Image:
    s = size * 4  # supersample
    im = background(s)
    d = ImageDraw.Draw(im)
    u = s / 1024  # design units
    ring_w = (92 if simple else 60) * u
    box = (170 * u, 170 * u, 854 * u, 854 * u)
    d.ellipse(box, outline=TRACK, width=int(ring_w))
    end = 200
    d.arc(box, -90, end, fill=GREEN, width=int(ring_w))
    r = (box[2] - box[0] - ring_w) / 2
    for ang in (-90, end):  # round caps
        cx = s / 2 + r * math.cos(math.radians(ang))
        cy = s / 2 + r * math.sin(math.radians(ang))
        d.ellipse((cx - ring_w / 2, cy - ring_w / 2, cx + ring_w / 2, cy + ring_w / 2), fill=GREEN)

    cx = s / 2
    if simple:
        layers = [(150, 60), (110, 60), (70, 60)]  # (half width, height) bottom-up
        bottom, gap = 640 * u, 26 * u
    else:
        # Nozzle
        nw, ny, nh = 70 * u, 292 * u, 92 * u
        d.rounded_rectangle((cx - nw, ny, cx + nw, ny + nh), radius=int(nw * 0.35), fill=WHITE)
        d.polygon([(cx - nw * 0.45, ny + nh - 2), (cx + nw * 0.45, ny + nh - 2), (cx, ny + nh + nw * 0.7)],
                  fill=GREEN)
        layers = [(150, 40), (124, 40), (98, 40), (72, 40)]
        bottom, gap = 690 * u, 18 * u
    y = bottom
    for half, h in layers:
        hw, hh = half * u, h * u
        d.rounded_rectangle((cx - hw, y - hh, cx + hw, y), radius=int(hh / 2), fill=WHITE)
        y -= hh + gap
    return im.resize((size, size), Image.LANCZOS)


def main() -> None:
    draw(1024).save(ASSETS / "logo.png")
    sizes = [16, 24, 32, 48, 64, 128, 256]
    frames = [draw(n, simple=n <= 32) for n in sizes]
    frames[-1].save(ASSETS / "app.ico", sizes=[(n, n) for n in sizes], append_images=frames[:-1])
    print("saved", ASSETS / "logo.png", ASSETS / "app.ico")


if __name__ == "__main__":
    main()
