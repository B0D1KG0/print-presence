"""Printer pictures for the app window.

Photos come from the Discord application's Rich Presence art assets (the same images
Discord shows in the status), so nothing copyrighted ships with the app. They're cached
on disk; until they arrive (or offline) the drawn icons from assets/ are used.
"""

from __future__ import annotations

import json
import logging
import math
import threading
import urllib.request
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw

log = logging.getLogger(__name__)

ASSETS_URL = "https://discord.com/api/v10/oauth2/applications/{app}/assets"
CDN_URL = "https://cdn.discordapp.com/app-assets/{app}/{asset}.png?size=512"
# Discord's CDN rejects requests without a browser-like or app User-Agent.
HEADERS = {"User-Agent": "PrintPresence (+https://github.com/B0D1KG0/print-presence)"}


def _get(url: str, timeout: float = 15.0) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=timeout) as resp:
        return resp.read()


def to_tile(im: Image.Image, radius: float = 0.16) -> Image.Image:
    """Crop transparent margins and round the corners — a product-card look."""
    im = im.convert("RGBA")
    solid = im.getchannel("A").point(lambda v: 255 if v > 250 else 0)
    box = solid.getbbox()
    if box:
        im = im.crop(box)
    side = max(im.size)
    if im.size[0] != im.size[1]:
        sq = Image.new("RGBA", (side, side), im.getpixel((0, 0)))
        sq.paste(im, ((side - im.width) // 2, (side - im.height) // 2), im)
        im = sq
    mask = Image.new("L", (side * 2, side * 2), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, side * 2 - 1, side * 2 - 1), radius=int(side * 2 * radius), fill=255)
    im.putalpha(mask.resize((side, side), Image.LANCZOS))
    return im


class PrinterArt:
    def __init__(self, local_dir: Path, cache_dir: Path, on_update: Callable[[], None]) -> None:
        self.local_dir = local_dir
        self.cache_dir = cache_dir
        self.on_update = on_update
        self.app_id: str | None = None
        self.remote: dict[str, Image.Image] = {}
        self._local: dict[str, Image.Image] = {}
        self._lock = threading.Lock()

    def local(self, name: str) -> Image.Image | None:
        if name not in self._local:
            try:
                self._local[name] = Image.open(self.local_dir / f"{name}.png").convert("RGBA")
            except OSError:
                return None
        return self._local[name]

    def photo(self, name: str) -> Image.Image:
        """Best picture for an image key like "printer_p1s"."""
        with self._lock:
            img = self.remote.get(name) or self.remote.get("printer")
        if img is None:
            img = self.local(name) or self.local("printer")
        return img or Image.new("RGBA", (256, 256), (31, 35, 43, 255))

    def use_app(self, app_id: str) -> None:
        """Load cached photos of this Discord app now, refresh them from Discord in the background."""
        if app_id == self.app_id:
            return
        self.app_id = app_id
        folder = self.cache_dir / app_id
        cached = {}
        for f in folder.glob("*.png"):
            name = f.stem.rsplit("-", 1)[0]
            try:
                cached[name] = to_tile(Image.open(f))
            except OSError:
                pass
        with self._lock:
            self.remote = cached
        threading.Thread(target=self._refresh, args=(app_id, folder), daemon=True).start()

    def _refresh(self, app_id: str, folder: Path) -> None:
        try:
            assets = json.loads(_get(ASSETS_URL.format(app=app_id)))
        except Exception as e:
            log.debug("Discord assets unavailable: %s", e)
            return
        changed = False
        folder.mkdir(parents=True, exist_ok=True)
        for asset in assets:
            name, asset_id = asset.get("name", ""), asset.get("id", "")
            if not (name == "printer" or name.startswith("printer_")) or not asset_id:
                continue
            path = folder / f"{name}-{asset_id}.png"
            try:
                if not path.exists():
                    for old in folder.glob(f"{name}-*.png"):
                        old.unlink(missing_ok=True)
                    path.write_bytes(_get(CDN_URL.format(app=app_id, asset=asset_id)))
                tile = to_tile(Image.open(path))
            except Exception as e:
                log.debug("Can't load %s: %s", name, e)
                continue
            with self._lock:
                if self.app_id != app_id:
                    return
                self.remote[name] = tile
            changed = True
        if changed:
            self.on_update()


def ring(percent: float | None, color: str, track: str, size: int = 104, width: int = 9) -> Image.Image:
    """Circular progress ring (drawn at 3x and scaled down for smooth edges)."""
    s = size * 3
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    w = width * 3
    box = (w // 2, w // 2, s - w // 2 - 1, s - w // 2 - 1)
    d.ellipse(box, outline=track, width=w)
    if percent:
        end = -90 + 360 * max(0.0, min(percent, 100.0)) / 100
        d.arc(box, -90, end, fill=color, width=w)
        # Round caps
        r = (s - w) / 2
        for angle in (-90, end):
            cx = s / 2 + r * math.cos(math.radians(angle))
            cy = s / 2 + r * math.sin(math.radians(angle))
            d.ellipse((cx - w / 2, cy - w / 2, cx + w / 2, cy + w / 2), fill=color)
    return im.resize((size, size), Image.LANCZOS)


def icon(name: str, color: str, size: int = 20) -> Image.Image:
    """Simple line icons for the sidebar and buttons (drawn at 4x for smooth edges)."""
    s = size * 4
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    w = max(4, s // 12)
    m = s * 0.14  # margin
    if name == "printers":  # 2x2 rounded tiles
        g = s * 0.08
        cell = (s - 2 * m - g) / 2
        for cx in (0, 1):
            for cy in (0, 1):
                x0, y0 = m + cx * (cell + g), m + cy * (cell + g)
                d.rounded_rectangle((x0, y0, x0 + cell, y0 + cell), radius=s * 0.06, outline=color, width=w)
    elif name == "settings":  # sliders
        for i, knob in enumerate((0.35, 0.68, 0.45)):
            y = m + (s - 2 * m) * (0.15 + 0.35 * i)
            d.line((m, y, s - m, y), fill=color, width=w)
            x = m + (s - 2 * m) * knob
            r = s * 0.085
            d.ellipse((x - r, y - r, x + r, y + r), fill=color)
    elif name == "log":  # lines of text
        for i, length in enumerate((1.0, 0.75, 0.9, 0.55)):
            y = m + (s - 2 * m) * (0.1 + 0.27 * i)
            d.line((m, y, m + (s - 2 * m) * length, y), fill=color, width=w)
    elif name == "about":  # circled "i"
        d.ellipse((m, m, s - m, s - m), outline=color, width=w)
        cx = s / 2
        d.ellipse((cx - w * 0.8, s * 0.3 - w * 0.8, cx + w * 0.8, s * 0.3 + w * 0.8), fill=color)
        d.line((cx, s * 0.43, cx, s * 0.7), fill=color, width=w)
    elif name == "search":
        r = (s - 2 * m) * 0.36
        cx = cy = m + r
        d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=color, width=w)
        d.line((cx + r * 0.7, cy + r * 0.7, s - m, s - m), fill=color, width=w)
    elif name == "plus":
        d.line((s / 2, m, s / 2, s - m), fill=color, width=w)
        d.line((m, s / 2, s - m, s / 2), fill=color, width=w)
    elif name == "play":
        d.polygon([(s * 0.3, s * 0.2), (s * 0.3, s * 0.8), (s * 0.8, s * 0.5)], fill=color)
    elif name == "stop":
        d.rounded_rectangle((s * 0.25, s * 0.25, s * 0.75, s * 0.75), radius=s * 0.06, fill=color)
    elif name == "copy":
        d.rounded_rectangle((m + s * 0.18, m, s - m, s - m - s * 0.18), radius=s * 0.06, outline=color, width=w)
        d.rounded_rectangle((m, m + s * 0.18, s - m - s * 0.18, s - m), radius=s * 0.06, outline=color, width=w)
    elif name == "folder":
        d.rounded_rectangle((m, s * 0.3, s - m, s - m), radius=s * 0.06, outline=color, width=w)
        d.line((m, s * 0.3, m + s * 0.25, s * 0.3), fill=color, width=w)
    elif name == "trash":
        d.line((m, s * 0.27, s - m, s * 0.27), fill=color, width=w)
        d.rounded_rectangle((s * 0.25, s * 0.27, s * 0.75, s - m), radius=s * 0.05, outline=color, width=w)
        d.line((s * 0.4, m, s * 0.6, m), fill=color, width=w)
    elif name == "chevron":
        d.line((s * 0.38, s * 0.22, s * 0.65, s * 0.5, s * 0.38, s * 0.78), fill=color, width=w, joint="curve")
    elif name == "arrow_up":
        d.line((s / 2, s - m, s / 2, m + w), fill=color, width=w)
        d.line((s * 0.25, s * 0.42, s / 2, m + w / 2, s * 0.75, s * 0.42), fill=color, width=w, joint="curve")
    return im.resize((size, size), Image.LANCZOS)
