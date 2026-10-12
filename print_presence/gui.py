"""Print Presence desktop window (CustomTkinter).

Layout: a sidebar with navigation and the Start/Stop button, and five pages —
Printers (dashboard), Constructor (own status templates), Settings, Log and About.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
import webbrowser
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

import customtkinter as ctk
from PIL import Image, ImageDraw

from . import __version__, i18n, settings, updates, winstartup
from .filament import filament_label
from .i18n import LANGUAGE_NAMES, tr
from .images import PrinterArt, icon, ring
from .presence import (BUTTON_LABEL, BUTTON_LIMIT, HIDEABLE, TEMPLATE_KEYS, VARIABLES, PrintClock, build_activity,
                       client_id_from, custom_options, render_lines, valid_url)
from .printers.bambu_discovery import FoundPrinter, discover, display_name, image_key
from .runner import Runner, status_language, validate
from .status import PrinterStatus, State
from .tray import Tray

log = logging.getLogger("print_presence")

REPO_URL = "https://github.com/B0D1KG0/print-presence"
DOCS = {
    "en": (REPO_URL + "#readme", REPO_URL + "#own-discord-application-optional"),
    "uk": (REPO_URL + "/blob/main/README.uk.md",
           REPO_URL + "/blob/main/README.uk.md#" + quote("власний-discord-застосунок-необовязково")),
    "ru": (REPO_URL + "/blob/main/README.ru.md",
           REPO_URL + "/blob/main/README.ru.md#" + quote("своё-discord-приложение-необязательно")),
}

# Palette
BG = "#0b0d12"
SIDEBAR = "#0f1218"
SURFACE = "#151922"
SURFACE_2 = "#1b202b"
SURFACE_3 = "#222836"
BORDER = "#232937"
BORDER_HOVER = "#323a4d"
TRACK = "#262c3a"
TEXT = "#eef0f4"
TEXT_2 = "#c4c9d4"
MUTED = "#8b93a4"
FAINT = "#5d6577"
GREEN = "#00ae42"
GREEN_HOVER = "#00973a"
GREEN_SOFT = "#0f2a1b"
RED = "#e5484d"
RED_HOVER = "#cc3d42"
RED_SOFT = "#2c1517"
AMBER = "#f5a623"
AMBER_SOFT = "#2c2212"
BLUE = "#3b9eff"
LINK = "#8fb0ff"
BLURPLE = "#5865f2"
DISCORD_BG = "#232428"
DISCORD_TEXT = "#dbdee1"

STATE_COLORS = {
    State.OFFLINE: MUTED,
    State.IDLE: MUTED,
    State.PREPARING: BLUE,
    State.PRINTING: GREEN,
    State.PAUSED: AMBER,
    State.FINISHED: BLUE,
    State.FAILED: RED,
}

_font_family: str | None = None


def font(size: int = 13, weight: str = "normal") -> ctk.CTkFont:
    global _font_family
    if _font_family is None:
        available = set(tkfont.families())
        _font_family = next((f for f in ("Segoe UI Variable Text", "Segoe UI", "Inter", "Helvetica Neue")
                             if f in available), "TkDefaultFont")
    return ctk.CTkFont(family=_font_family, size=size, weight=weight)


def docs_url(custom_app: bool = False) -> str:
    return DOCS.get(i18n.current(), DOCS["en"])[1 if custom_app else 0]


def resource(name: str) -> Path:
    # Files bundled by PyInstaller live in sys._MEIPASS.
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / name


def fmt_minutes(minutes: int | None, short: bool = False) -> str:
    if not minutes:
        return "—"
    h, m = divmod(int(minutes), 60)
    if short:
        return f"{h}:{m:02d}"
    return tr("time.hm", h=h, m=m) if h else tr("time.m", m=m)


def printer_name(p: dict[str, Any]) -> str:
    return str(p.get("name") or "").strip() or display_name(p.get("model_code"), p.get("serial"))


def printer_image(p: dict[str, Any]) -> str:
    return image_key(p.get("model_code"), p.get("serial"))


def is_empty(p: dict[str, Any]) -> bool:
    return not any(str(p.get(k) or "").strip() for k in ("host", "serial", "access_code", "name"))


def bind_tree(widget: tk.Misc, event: str, handler: Callable[[Any], Any], cursor: bool = False) -> None:
    widget.bind(event, handler, add="+")
    if cursor:
        try:
            widget.configure(cursor="hand2")
        except (tk.TclError, ValueError):
            pass
    for child in widget.winfo_children():
        bind_tree(child, event, handler, cursor)


def bind_click(widget: tk.Misc, command: Callable[[], None]) -> None:
    bind_tree(widget, "<Button-1>", lambda _e: command(), cursor=True)


class QueueHandler(logging.Handler):
    def __init__(self, q: queue.Queue) -> None:
        super().__init__()
        self.q = q
        self.setFormatter(logging.Formatter("%(asctime)s  %(message)s", "%H:%M:%S"))

    def emit(self, record: logging.LogRecord) -> None:
        self.q.put(("log", (record.levelno, self.format(record))))


class Images:
    """CTkImage cache: printer photos, Discord previews, rings and icons."""

    def __init__(self, art: PrinterArt) -> None:
        self.art = art
        self.cache: dict[tuple, ctk.CTkImage] = {}

    def clear(self) -> None:
        self.cache = {k: v for k, v in self.cache.items() if k[0] in ("icon", "ring")}

    def photo(self, key: str, size: int) -> ctk.CTkImage:
        k = ("photo", key, size)
        if k not in self.cache:
            self.cache[k] = ctk.CTkImage(self.art.photo(key), size=(size, size))
        return self.cache[k]

    def preview(self, key: str, badge: str | None, size: int = 72) -> ctk.CTkImage:
        """Discord-style large image with the small status badge in the corner."""
        k = ("preview", key, badge, size)
        if k not in self.cache:
            big, pad = 240, 30
            img = Image.new("RGBA", (big + pad, big + pad), (0, 0, 0, 0))
            photo = self.art.photo(key).resize((big, big), Image.LANCZOS)
            img.paste(photo, (0, 0), photo)
            small = self.art.local(badge) if badge else None
            if small is not None:
                small = small.resize((96, 96), Image.LANCZOS)
                circle = Image.new("RGBA", (116, 116), (0, 0, 0, 0))
                ImageDraw.Draw(circle).ellipse((0, 0, 115, 115), fill=DISCORD_BG)
                circle.paste(small, (10, 10), small)
                img.paste(circle, (big + pad - 116, big + pad - 116), circle)
            self.cache[k] = ctk.CTkImage(img, size=(size, size))
        return self.cache[k]

    def ring(self, percent: float | None, color: str, size: int = 92) -> ctk.CTkImage:
        k = ("ring", round(percent or 0), color, size)
        if k not in self.cache:
            self.cache[k] = ctk.CTkImage(ring(percent, color, TRACK, size=size, width=8), size=(size, size))
        return self.cache[k]

    def icon(self, name: str, color: str, size: int = 18) -> ctk.CTkImage:
        k = ("icon", name, color, size)
        if k not in self.cache:
            self.cache[k] = ctk.CTkImage(icon(name, color, size), size=(size, size))
        return self.cache[k]


# Small building blocks ---------------------------------------------------------


class Surface(ctk.CTkFrame):
    """A card with the standard look."""

    def __init__(self, master: Any, **kw: Any) -> None:
        kw.setdefault("fg_color", SURFACE)
        kw.setdefault("border_color", BORDER)
        kw.setdefault("border_width", 1)
        kw.setdefault("corner_radius", 16)
        super().__init__(master, **kw)
        self.grid_columnconfigure(0, weight=1)


def section_label(master: Any, text: str) -> ctk.CTkLabel:
    return ctk.CTkLabel(master, text=text.upper(), font=font(11, "bold"), text_color=FAINT, anchor="w")


def ghost_button(master: Any, text: str, image: ctk.CTkImage | None, command: Callable[[], None],
                 danger: bool = False) -> ctk.CTkButton:
    return ctk.CTkButton(master, text=text, image=image, compound="left", command=command, height=34,
                         corner_radius=10, font=font(13), fg_color=SURFACE_2, hover_color=SURFACE_3,
                         border_width=1, border_color=BORDER, text_color="#ff9a9e" if danger else TEXT_2)


class Field(ctk.CTkFrame):
    """Label + entry + hint line."""

    def __init__(self, master: Any, label: str, hint: str = "", value: str = "", secret: bool = False,
                 placeholder: str = "") -> None:
        super().__init__(master, fg_color="transparent")
        self.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self, text=label, font=font(12, "bold"), text_color=TEXT_2, anchor="w").grid(
            row=0, column=0, sticky="w")
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        row.grid_columnconfigure(0, weight=1)
        # No textvariable: CTkEntry placeholders only work without one.
        self.entry = ctk.CTkEntry(row, height=38, corner_radius=10, font=font(13), fg_color=BG,
                                  border_color=BORDER, border_width=1, text_color=TEXT,
                                  placeholder_text_color=FAINT, placeholder_text=placeholder or None)
        self.entry.grid(row=0, column=0, sticky="ew")
        self.secret, self.revealed = secret, False
        if secret:
            self.entry.configure(show="•")
            ctk.CTkButton(row, text="👁", width=38, height=38, corner_radius=10, fg_color=BG,
                          hover_color=SURFACE_3, border_width=1, border_color=BORDER, text_color=MUTED,
                          command=self._toggle).grid(row=0, column=1, padx=(6, 0))
        if hint:
            ctk.CTkLabel(self, text=hint, font=font(11), text_color=FAINT, anchor="w", justify="left",
                         wraplength=320).grid(row=2, column=0, sticky="w", pady=(4, 0))
        if value:
            self.set(value)

    def _toggle(self) -> None:
        self.revealed = not self.revealed
        if self.entry.get():
            self.entry.configure(show="" if self.revealed else "•")

    def get(self) -> str:
        return self.entry.get().strip()

    def set(self, value: str) -> None:
        state = self.entry.cget("state")
        self.entry.configure(state="normal")
        self.entry.delete(0, "end")
        if value:
            self.entry.insert(0, value)
            if self.secret:
                # Restoring the pre-placeholder state can lose the mask; set it explicitly.
                self.entry.configure(show="" if self.revealed else "•")
        else:
            # CTkEntry only shows its placeholder again after losing focus; show it right away.
            activate = getattr(self.entry, "_activate_placeholder", None)
            if activate:
                activate()
        self.entry.configure(state=state)

    def enable(self, on: bool) -> None:
        self.entry.configure(state="normal" if on else "disabled", text_color=TEXT if on else MUTED)


class SettingRow(ctk.CTkFrame):
    """Title + description on the left, a control on the right."""

    def __init__(self, master: Any, title: str, desc: str = "", divider: bool = True, wrap: int = 480) -> None:
        super().__init__(master, fg_color="transparent")
        self.grid_columnconfigure(0, weight=1)
        if divider:
            ctk.CTkFrame(self, fg_color=BORDER, height=1, corner_radius=0).grid(
                row=0, column=0, columnspan=2, sticky="ew")
        self.text = ctk.CTkFrame(self, fg_color="transparent")
        self.text.grid(row=1, column=0, sticky="w", pady=14)
        ctk.CTkLabel(self.text, text=title, font=font(14, "bold"), text_color=TEXT, anchor="w").pack(anchor="w")
        if desc:
            ctk.CTkLabel(self.text, text=desc, font=font(12), text_color=MUTED, anchor="w", justify="left",
                         wraplength=wrap).pack(anchor="w", pady=(2, 0))
        self.control_parent = self

    def place_control(self, widget: Any) -> Any:
        widget.grid(row=1, column=1, sticky="e", padx=(16, 0))
        return widget

    def place_below(self, widget: Any) -> Any:
        """For wide controls: under the title instead of next to it."""
        self.text.grid_configure(pady=(14, 8))
        widget.grid(row=2, column=0, columnspan=2, sticky="w", pady=(0, 14))
        return widget


class DiscordCard(ctk.CTkFrame):
    """Mock-up of the activity the way Discord draws it in a profile."""

    HEADERS = {0: "home.playing", 2: "home.listening", 3: "home.watching", 5: "home.competing"}

    def __init__(self, master: Any, images: Images) -> None:
        super().__init__(master, fg_color=DISCORD_BG, corner_radius=12)
        self.images = images
        self.grid_columnconfigure(1, weight=1)
        self.header = ctk.CTkLabel(self, text=tr("home.playing"), font=font(11, "bold"), text_color="#b5bac1",
                                   height=16)
        self.header.grid(row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(14, 8))
        self.image = ctk.CTkLabel(self, text="")
        self.image.grid(row=1, column=0, rowspan=4, sticky="nw", padx=(16, 12))
        self.title = ctk.CTkLabel(self, text="", font=font(14, "bold"), text_color="#f2f3f5", anchor="w", height=20)
        self.title.grid(row=1, column=1, sticky="w")
        self.details = ctk.CTkLabel(self, text="", font=font(13), text_color=DISCORD_TEXT, anchor="w", height=18)
        self.details.grid(row=2, column=1, sticky="w")
        self.state = ctk.CTkLabel(self, text="", font=font(13), text_color=DISCORD_TEXT, anchor="w", height=18)
        self.state.grid(row=3, column=1, sticky="w")
        self.time = ctk.CTkLabel(self, text="", font=font(12), text_color="#23a55a", anchor="w", height=18)
        self.time.grid(row=4, column=1, sticky="nw")
        self.buttons = [ctk.CTkLabel(self, text="", font=font(13, "bold"), fg_color="#3a3c42", corner_radius=8,
                                     text_color="#f2f3f5", height=34) for _ in range(2)]
        ctk.CTkFrame(self, fg_color="transparent", height=14).grid(row=7, column=0, columnspan=2)

    def show(self, title: str, image_key: str, activity: dict[str, Any] | None, remaining: int | None = None,
             empty_text: str = "", button: bool = True, now: float | None = None) -> str:
        """Draw the activity (or empty_text when there is none); returns a one-line summary."""
        self.title.configure(text=title)
        labels = [BUTTON_LABEL] if button else []
        if activity is None:
            self.header.configure(text=tr("home.playing"))
            self.image.configure(image=self.images.preview(image_key, None))
            self.details.configure(text=empty_text)
            self.state.configure(text="")
            self.time.configure(text="")
            line = empty_text
        else:
            self.header.configure(text=tr(self.HEADERS.get(activity.get("activity_type", 0), "home.playing")))
            self.image.configure(image=self.images.preview(image_key, activity.get("small_image")))
            details, state = activity["details"].strip(), activity.get("state", "").strip()
            party = activity.get("party_size")
            shown_state = f"{state} ({tr('cons.party', a=party[0], b=party[1])})".strip() if party else state
            self.details.configure(text=details)
            self.state.configure(text=shown_state)
            if activity.get("end") and remaining:
                self.time.configure(text=tr("home.time_left", time=fmt_minutes(remaining)))
            elif activity.get("start"):
                spent = max(0, int(((time.time() if now is None else now) - activity["start"]) // 60))
                self.time.configure(text=tr("home.elapsed", time=fmt_minutes(spent) if spent else "0:00"))
            else:
                self.time.configure(text="")
            labels = [b["label"] for b in activity.get("buttons", [])]
            line = " · ".join(x for x in (details, state) if x)
        for i, widget in enumerate(self.buttons):
            if i < len(labels):
                widget.configure(text=labels[i])
                widget.grid(row=5 + i, column=0, columnspan=2, sticky="ew", padx=16, pady=(12 if i == 0 else 8, 0))
            else:
                widget.grid_remove()
        return line


class TemplateField(ctk.CTkFrame):
    """One constructor line: title (+ show/hide switch), entry, hint and a length counter."""

    def __init__(self, master: Any, label: str, hint: str = "", toggle: bool = False) -> None:
        super().__init__(master, fg_color="transparent")
        self.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self, text=label, font=font(12, "bold"), text_color=TEXT_2, anchor="w").grid(
            row=0, column=0, sticky="w")
        self.shown: tk.BooleanVar | None = None
        self.switch: ctk.CTkSwitch | None = None
        if toggle:
            self.shown = tk.BooleanVar(value=True)
            self.switch = ctk.CTkSwitch(self, text="", variable=self.shown, width=40, switch_width=36,
                                        switch_height=18, progress_color=GREEN, button_color="#ffffff",
                                        button_hover_color="#e6e6e6", fg_color=SURFACE_3)
            self.switch.grid(row=0, column=1, sticky="e")
        self.entry = ctk.CTkEntry(self, height=38, corner_radius=10, font=font(13), fg_color=BG,
                                  border_color=BORDER, border_width=1, text_color=TEXT)
        self.entry.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        self.hint = ctk.CTkLabel(self, text=hint, font=font(11), text_color=FAINT, anchor="w", justify="left",
                                 wraplength=360)
        self.hint.grid(row=2, column=0, sticky="w", pady=(3, 0))
        self.counter = ctk.CTkLabel(self, text="", font=font(11), text_color=FAINT, anchor="e")
        self.counter.grid(row=2, column=1, sticky="e", pady=(3, 0))

    def get(self) -> str:
        return self.entry.get()

    def set(self, value: str) -> None:
        state = self.entry.cget("state")
        self.entry.configure(state="normal")
        self.entry.delete(0, "end")
        self.entry.insert(0, value)
        self.entry.configure(state=state)

    def enable(self, on: bool, toggle: bool | None = None) -> None:
        self.entry.configure(state="normal" if on else "disabled", text_color=TEXT if on else MUTED)
        if self.switch is not None:
            self.switch.configure(state="normal" if (on if toggle is None else toggle) else "disabled")

    def count(self, used: int, limit: int, unit: str = "") -> None:
        self.counter.configure(text=f"{used}/{limit}{unit}", text_color=RED if used > limit else FAINT)


class PrinterCard(ctk.CTkFrame):
    """One printer on the dashboard: photo, progress ring, job and a few numbers."""

    def __init__(self, master: Any, images: Images, on_click: Callable[[], None]) -> None:
        super().__init__(master, fg_color=SURFACE, corner_radius=18, border_width=1, border_color=BORDER)
        self.images = images
        self.featured = False
        self.grid_columnconfigure(0, weight=1)

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 0))
        head.grid_columnconfigure(1, weight=1)
        self.dot = ctk.CTkLabel(head, text="●", font=font(12), text_color=MUTED, width=14)
        self.dot.grid(row=0, column=0, padx=(0, 6))
        self.name = ctk.CTkLabel(head, text="", font=font(14, "bold"), text_color=TEXT, anchor="w")
        self.name.grid(row=0, column=1, sticky="w")
        self.state = ctk.CTkLabel(head, text="", font=font(11, "bold"), corner_radius=8, height=22)
        self.state.grid(row=0, column=2, sticky="e")

        mid = ctk.CTkFrame(self, fg_color="transparent")
        mid.grid(row=1, column=0, sticky="ew", padx=18, pady=(14, 0))
        mid.grid_columnconfigure(1, weight=1)
        self.photo = ctk.CTkLabel(mid, text="")
        self.photo.grid(row=0, column=0, sticky="w")
        self.ring = ctk.CTkLabel(mid, text="", font=font(20, "bold"), text_color=TEXT, compound="center")
        self.ring.grid(row=0, column=2, sticky="e")

        self.job = ctk.CTkLabel(self, text="", font=font(16, "bold"), text_color=TEXT, anchor="w")
        self.job.grid(row=2, column=0, sticky="w", padx=18, pady=(14, 0))
        self.sub = ctk.CTkLabel(self, text="", font=font(12), text_color=MUTED, anchor="w")
        self.sub.grid(row=3, column=0, sticky="w", padx=18)

        ctk.CTkFrame(self, fg_color=BORDER, height=1, corner_radius=0).grid(
            row=4, column=0, sticky="ew", padx=18, pady=(14, 0))
        stats = ctk.CTkFrame(self, fg_color="transparent")
        stats.grid(row=5, column=0, sticky="ew", padx=18, pady=(10, 16))
        self.values: list[tuple[ctk.CTkLabel, ctk.CTkLabel]] = []
        for i in range(3):
            stats.grid_columnconfigure(i, weight=1, uniform="s")
            col = ctk.CTkFrame(stats, fg_color="transparent")
            col.grid(row=0, column=i, sticky="w")
            label = ctk.CTkLabel(col, text="", font=font(11), text_color=FAINT, height=16)
            label.pack(anchor="w")
            value = ctk.CTkLabel(col, text="—", font=font(14, "bold"), text_color=TEXT_2, height=20)
            value.pack(anchor="w")
            self.values.append((label, value))
        bind_click(self, on_click)
        bind_tree(self, "<Enter>", lambda _e: self._hover(True))
        bind_tree(self, "<Leave>", lambda _e: self._hover(False))

    def _hover(self, on: bool) -> None:
        if not self.featured:
            self.configure(border_color=BORDER_HOVER if on else BORDER)

    def show(self, p: dict[str, Any], s: PrinterStatus | None, featured: bool, running: bool) -> None:
        state = s.state if s else State.OFFLINE
        color = STATE_COLORS[state]
        self.featured = featured
        self.configure(border_color=GREEN if featured else BORDER, border_width=2 if featured else 1)
        self.dot.configure(text_color=color if running else FAINT)
        self.name.configure(text=printer_name(p))
        if running and s is not None:
            soft = {GREEN: GREEN_SOFT, AMBER: AMBER_SOFT, RED: RED_SOFT, BLUE: "#13243a"}.get(color, SURFACE_2)
            self.state.configure(text=f"  {tr(f'state.{state.value}')}  ", text_color=color, fg_color=soft)
        else:
            self.state.configure(text=f"  {p.get('host', '')}  ", text_color=FAINT, fg_color="transparent")
        self.photo.configure(image=self.images.photo(printer_image(p), 96))

        if not running or s is None:
            ring_text, pct = "—", None
        elif state in (State.PRINTING, State.PAUSED):
            ring_text, pct = f"{s.progress or 0}%", s.progress or 0
        elif state == State.FINISHED:
            ring_text, pct = "✓", 100
        else:
            ring_text, pct = "—", None
        self.ring.configure(image=self.images.ring(pct, color), text=ring_text,
                            text_color=TEXT if pct is not None else FAINT)

        if not running:
            job, sub = tr("home.not_started"), tr("card.edit")
        elif s is None or state == State.OFFLINE:
            job, sub = tr("home.unreachable"), p.get("host", "")
        else:
            job = tr("home.calibration") if s.calibration else (s.job_name or tr("home.no_job"))
            sub = filament_label(s.filament, s.filament_color, i18n.current()) or tr(f"state.{state.value}")
        self.job.configure(text=job if len(job) <= 30 else job[:29] + "…")
        self.sub.configure(text=sub)

        layer = f"{s.layer}/{s.total_layers}" if s and s.total_layers else "—"
        left = fmt_minutes(s.remaining_min, short=True) if s and state == State.PRINTING else "—"
        nozzle = f"{s.nozzle_temp:.0f}°" if s and s.nozzle_temp is not None else "—"
        for (label, value), (name, text) in zip(self.values, (
                (tr("tile.layer"), layer), (tr("tile.left"), left), (tr("tile.nozzle"), nozzle))):
            label.configure(text=name)
            value.configure(text=text)


class App:
    def __init__(self, root: ctk.CTk, minimized: bool = False) -> None:
        self.root = root
        self.cfg = settings.load()
        self.printers: list[dict[str, Any]] = [dict(p) for p in self.cfg["printers"]] or [
            dict(settings.EMPTY_PRINTER)]
        self.sel = 0
        self.runner: Runner | None = None
        self.run_printers: list[dict[str, Any]] = []
        self.statuses: list[PrinterStatus] = []
        self.featured = 0
        self.discord_ok = False
        self.update_info: tuple[str, str] | None = None
        self.events: queue.Queue = queue.Queue()
        self.searching = False
        self.cards: list[PrinterCard] = []
        self.columns = 0
        self.page = "printers"
        self.log_lines: list[tuple[int, str]] = []
        self.status_line = ""
        self._push_job: str | None = None
        self.template_entries: dict[str, Any] = {}
        self.focused_template = "details"
        self.clocks: list[PrintClock] = []

        cache = settings.settings_path().parent / "cache"
        self.art = PrinterArt(resource("assets"), cache, lambda: self.events.put(("art", None)))
        self.art.use_app(client_id_from(self.cfg))
        self.images = Images(self.art)

        # Only our own messages go to the Log page; third-party libraries stay out of it.
        app_logger = logging.getLogger("print_presence")
        app_logger.addHandler(QueueHandler(self.events))
        app_logger.setLevel(logging.INFO)

        root.title("Print Presence")
        root.geometry("1180x760")
        root.minsize(980, 640)
        root.configure(fg_color=BG)
        self._set_icon()

        self.tray = Tray(self._app_icon(), self.events, self._running)
        self._build()
        self._refresh_view()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.after(200, self._poll)

        if minimized and self.tray.available:
            root.withdraw()
        if winstartup.is_enabled():
            winstartup.set_enabled(True)  # refresh the path in case the exe was moved
        if not self.printers[0].get("host"):
            root.after(400, self.search)  # first launch: look for printers right away
        elif self.cfg["app"].get("autostart") or minimized:
            root.after(500, self.start)
        if self.cfg["app"].get("check_updates", True):
            self._check_updates()

    def _app_icon(self) -> Image.Image:
        return self.art.local("logo") or self.art.local("printer") or Image.new("RGBA", (64, 64), (31, 35, 43, 255))

    def _set_icon(self) -> None:
        ico = resource("assets/app.ico")
        if sys.platform == "win32" and ico.exists():
            # CustomTkinter sets its own icon shortly after start; override it after that.
            self.root.after(250, lambda: self.root.iconbitmap(str(ico)))
        else:
            try:
                self._icon = tk.PhotoImage(file=resource("assets/logo.png")).subsample(8)
                self.root.iconphoto(True, self._icon)
            except tk.TclError:
                pass

    def _running(self) -> bool:
        return self.runner is not None and self.runner.running

    # Layout ----------------------------------------------------------------

    def _build(self) -> None:
        root = self.root
        root.grid_columnconfigure(1, weight=1)
        root.grid_rowconfigure(0, weight=1)
        self.cards = []
        self.columns = 0
        self.PAGES = {"printers": tr("tab.farm"), "presence": tr("nav.constructor"), "settings": tr("tab.settings"),
                      "log": tr("tab.log"), "about": tr("nav.about")}
        self._build_sidebar()

        main = ctk.CTkFrame(root, fg_color=BG, corner_radius=0)
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(0, weight=1)
        self.pages: dict[str, ctk.CTkFrame] = {}
        # Settings first: the constructor preview reads its switches.
        builders = {"settings": self._build_settings, "printers": self._build_printers,
                    "presence": self._build_constructor, "log": self._build_log, "about": self._build_about}
        for key, build in builders.items():
            page = ctk.CTkFrame(main, fg_color=BG, corner_radius=0)
            page.grid(row=0, column=0, sticky="nsew")
            page.grid_columnconfigure(0, weight=1)
            page.grid_rowconfigure(1, weight=1)
            self.pages[key] = page
            build(page)
        self.show_page(self.page)
        self._update_button()

    def _page_header(self, page: ctk.CTkFrame, key: str, subtitle: str) -> ctk.CTkFrame:
        head = ctk.CTkFrame(page, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=32, pady=(28, 18))
        head.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(head, text=self.PAGES[key], font=font(26, "bold"), text_color=TEXT, anchor="w",
                     height=34).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(head, text=subtitle, font=font(13), text_color=MUTED, anchor="w").grid(
            row=1, column=0, sticky="w")
        # height=1: an empty CTkFrame would otherwise reserve its default 200 px
        actions = ctk.CTkFrame(head, fg_color="transparent", height=1)
        actions.grid(row=0, column=1, rowspan=2, sticky="e")
        return actions

    def _build_sidebar(self) -> None:
        side = ctk.CTkFrame(self.root, fg_color=SIDEBAR, corner_radius=0, width=236)
        side.grid(row=0, column=0, sticky="ns")
        side.grid_propagate(False)
        side.grid_columnconfigure(0, weight=1)
        side.grid_rowconfigure(2, weight=1)
        ctk.CTkFrame(self.root, fg_color=BORDER, width=1, corner_radius=0).grid(row=0, column=0, sticky="nse")

        brand = ctk.CTkFrame(side, fg_color="transparent")
        brand.grid(row=0, column=0, sticky="ew", padx=20, pady=(24, 26))
        self._logo = ctk.CTkImage(self._app_icon(), size=(36, 36))
        ctk.CTkLabel(brand, image=self._logo, text="").grid(row=0, column=0, rowspan=2, padx=(0, 12))
        ctk.CTkLabel(brand, text="Print Presence", font=font(16, "bold"), text_color=TEXT, height=20,
                     anchor="w").grid(row=0, column=1, sticky="sw")
        ctk.CTkLabel(brand, text=f"v{__version__}" + (" · Portable" if settings.is_portable() else ""),
                     font=font(11), text_color=FAINT, height=14,
                     anchor="w").grid(row=1, column=1, sticky="nw")

        nav = ctk.CTkFrame(side, fg_color="transparent")
        nav.grid(row=1, column=0, sticky="ew", padx=12)
        nav.grid_columnconfigure(0, weight=1)
        self.nav_items: dict[str, ctk.CTkButton] = {}
        for i, key in enumerate(self.PAGES):
            btn = ctk.CTkButton(nav, text=f"  {self.PAGES[key]}", anchor="w", height=42, corner_radius=10,
                                font=font(14), fg_color="transparent", hover_color=SURFACE,
                                image=self.images.icon(key, MUTED), compound="left",
                                command=lambda k=key: self.show_page(k))
            btn.grid(row=i, column=0, sticky="ew", pady=2)
            self.nav_items[key] = btn

        bottom = ctk.CTkFrame(side, fg_color="transparent")
        bottom.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 20))
        bottom.grid_columnconfigure(0, weight=1)
        self.update_btn = ctk.CTkButton(bottom, text="", height=36, corner_radius=10, font=font(12, "bold"),
                                        fg_color=GREEN_SOFT, hover_color="#163b26", text_color="#6fe3a0",
                                        image=self.images.icon("arrow_up", "#6fe3a0", 14), compound="left",
                                        command=lambda: self.update_info and webbrowser.open(self.update_info[1]))
        if self.update_info:
            self._show_update(self.update_info)
        status = ctk.CTkFrame(bottom, fg_color=SURFACE, corner_radius=12, border_width=1, border_color=BORDER)
        status.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        status.grid_columnconfigure(1, weight=1)
        self.pill_dot = ctk.CTkLabel(status, text="●", font=font(12), text_color=MUTED, width=16)
        self.pill_dot.grid(row=0, column=0, padx=(12, 4), pady=10)
        self.pill = ctk.CTkLabel(status, text="", font=font(12, "bold"), text_color=TEXT_2, anchor="w")
        self.pill.grid(row=0, column=1, sticky="w", pady=10)
        self.button = ctk.CTkButton(bottom, text="", height=46, corner_radius=12, font=font(14, "bold"),
                                    compound="left", command=self.toggle)
        self.button.grid(row=2, column=0, sticky="ew")

    def show_page(self, key: str) -> None:
        key = next((k for k, v in self.PAGES.items() if key in (k, v)), "printers")
        self.page = key
        self.pages[key].tkraise()
        for k, btn in self.nav_items.items():
            on = k == key
            btn.configure(fg_color=SURFACE_2 if on else "transparent", text_color=TEXT if on else MUTED,
                          image=self.images.icon(k, TEXT if on else MUTED),
                          font=font(14, "bold" if on else "normal"))

    # Printers page ---------------------------------------------------------

    def _build_printers(self, page: ctk.CTkFrame) -> None:
        actions = self._page_header(page, "printers", tr("page.printers"))
        self.dash_find = ghost_button(actions, tr("set.find").replace("🔍", "").strip(),
                                      self.images.icon("search", TEXT_2, 15), self._find_from_dashboard)
        self.dash_find.grid(row=0, column=0, padx=(0, 8))
        self.dash_add = ghost_button(actions, tr("set.add_printer").replace("+", "").strip(),
                                     self.images.icon("plus", TEXT_2, 15), self._add_from_farm)
        self.dash_add.grid(row=0, column=1)

        body = ctk.CTkScrollableFrame(page, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=(20, 12), pady=(0, 16))
        body.grid_columnconfigure(0, weight=1)
        self.dash_body = body

        # Hero: what Discord shows + quick stats
        hero = Surface(body)
        hero.grid(row=0, column=0, sticky="ew", padx=12, pady=(0, 22))
        hero.grid_columnconfigure(0, weight=3)
        hero.grid_columnconfigure(1, weight=2)
        left = ctk.CTkFrame(hero, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(20, 10), pady=20)
        left.grid_columnconfigure(0, weight=1)
        section_label(left, tr("home.preview")).grid(row=0, column=0, sticky="w", pady=(0, 10))
        self.hero_card = DiscordCard(left, self.images)
        self.hero_card.grid(row=1, column=0, sticky="ew")

        right = ctk.CTkFrame(hero, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", padx=(10, 20), pady=20)
        right.grid_columnconfigure(0, weight=1)
        self.hero_stats: dict[str, tuple[ctk.CTkLabel, ctk.CTkLabel]] = {}
        for i, key in enumerate(("printing", "discord")):
            box = ctk.CTkFrame(right, fg_color=SURFACE_2, corner_radius=12)
            box.grid(row=i, column=0, sticky="ew", pady=(0 if i == 0 else 10, 0))
            label = ctk.CTkLabel(box, text=tr(f"hero.{key}"), font=font(12), text_color=MUTED, anchor="w")
            label.pack(anchor="w", padx=16, pady=(12, 0))
            value = ctk.CTkLabel(box, text="—", font=font(20, "bold"), text_color=TEXT, anchor="w")
            value.pack(anchor="w", padx=16, pady=(0, 12))
            self.hero_stats[key] = (label, value)

        section_label(body, tr("set.printers")).grid(row=1, column=0, sticky="w", padx=14, pady=(0, 8))
        self.grid = ctk.CTkFrame(body, fg_color="transparent")
        self.grid.grid(row=2, column=0, sticky="ew", padx=6)
        self.grid.bind("<Configure>", lambda _e: self._layout_cards(), add="+")

        self.add_card = ctk.CTkFrame(self.grid, fg_color="transparent", corner_radius=18, border_width=2,
                                     border_color=BORDER, height=318)
        self.add_card.grid_propagate(False)
        self.add_card.grid_columnconfigure(0, weight=1)
        self.add_card.grid_rowconfigure((0, 4), weight=1)
        plus = ctk.CTkFrame(self.add_card, fg_color=SURFACE_2, corner_radius=24, width=48, height=48)
        plus.grid(row=1, column=0)
        plus.grid_propagate(False)
        ctk.CTkLabel(plus, text="", image=self.images.icon("plus", TEXT_2, 20)).place(relx=0.5, rely=0.5,
                                                                                      anchor="center")
        ctk.CTkLabel(self.add_card, text=tr("card.add"), font=font(14, "bold"), text_color=TEXT_2).grid(
            row=2, column=0, pady=(12, 0))
        ctk.CTkLabel(self.add_card, text=tr("card.add_hint"), font=font(12), text_color=FAINT).grid(row=3, column=0)
        bind_click(self.add_card, self._add_from_farm)
        bind_tree(self.add_card, "<Enter>", lambda _e: self.add_card.configure(border_color=BORDER_HOVER))
        bind_tree(self.add_card, "<Leave>", lambda _e: self.add_card.configure(border_color=BORDER))

    def _shown_printers(self) -> list[dict[str, Any]]:
        if self._running():
            return self.run_printers
        return [p for p in self.printers if not is_empty(p)]

    def _layout_cards(self, force: bool = False) -> None:
        width = self.grid.winfo_width()
        cols = 3 if width >= 900 else 2 if width >= 560 else 1
        if cols == self.columns and not force:
            return
        self.columns = cols
        for c in range(3):
            self.grid.grid_columnconfigure(c, weight=1 if c < cols else 0, uniform="cards" if c < cols else "")
        items: list[ctk.CTkFrame] = list(self.cards)
        if not self._running():
            items.append(self.add_card)
        else:
            self.add_card.grid_remove()
        for i, item in enumerate(items):
            item.grid(row=i // cols, column=i % cols, sticky="new", padx=6, pady=6)

    def _sync_cards(self) -> None:
        printers = self._shown_printers()
        while len(self.cards) < len(printers):
            idx = len(self.cards)
            self.cards.append(PrinterCard(self.grid, self.images, lambda i=idx: self.open_printer(i)))
        while len(self.cards) > len(printers):
            self.cards.pop().destroy()
        self._layout_cards(force=True)
        running = self._running()
        for i, (card, p) in enumerate(zip(self.cards, printers)):
            s = self.statuses[i] if running and i < len(self.statuses) else None
            card.show(p, s, featured=running and bool(self.statuses) and i == self.featured, running=running)

    def _show_hero(self) -> None:
        printers = self._shown_printers()
        if self._running() and self.statuses and self.featured < len(printers):
            p, s = printers[self.featured], self.statuses[self.featured]
        else:
            p = printers[0] if printers else self.printers[self.sel]
            s = None
        start = self.clocks[self.featured].start if s and self.featured < len(self.clocks) else None
        activity = self._activity(s, printer_name(p), start) if s else None
        if not self._running():
            empty = tr("home.press_start")
        elif s is None or s.state == State.OFFLINE:
            empty = tr("home.hidden")
        else:
            empty = tr("strip.off")
        self.status_line = self.hero_card.show(printer_name(p), printer_image(p), activity,
                                               s.remaining_min if s else None, empty, self.show_button.get())

        total = len(printers)
        printing = sum(1 for st in self.statuses if st.state in (State.PRINTING, State.PAUSED, State.PREPARING)) \
            if self._running() else 0
        self.hero_stats["printing"][1].configure(text=tr("hero.of", a=printing, b=total) if total else "—")
        ok = self._running() and self.discord_ok
        self.hero_stats["discord"][1].configure(
            text=tr("hero.connected") if ok else tr("hero.not_connected"), text_color=GREEN if ok else MUTED)

    def _refresh_view(self) -> None:
        self._sync_cards()
        self._show_hero()
        self._show_constructor_preview()

    def _activity(self, status: PrinterStatus, name: str, started: float | None = None) -> dict[str, Any] | None:
        """The activity with the options currently set in the window."""
        if status.state == State.IDLE and not self.show_idle.get():
            return None
        return build_activity(status, name, self._lang_code(), hide_job=self.hide_job.get(),
                              button=self.show_button.get(), custom=self._custom_opts(), started=started)

    def open_printer(self, index: int) -> None:
        printers = self._shown_printers()
        if index < len(printers) and not self._running():
            target = printers[index]
            self._store_fields()
            self._select(next((i for i, p in enumerate(self.printers) if p is target), self.sel))
        self.show_page("settings")

    def _add_from_farm(self) -> None:
        if self._running():
            return
        self.show_page("settings")
        if is_empty(self.printers[-1]):
            self._select(len(self.printers) - 1)
        else:
            self._add_printer()
        self.search()

    def _find_from_dashboard(self) -> None:
        self.show_page("settings")
        self.search()

    # Constructor page ------------------------------------------------------

    SAMPLE = PrinterStatus(state=State.PRINTING, job_name="Benchy.3mf", progress=42, layer=87, total_layers=240,
                           remaining_min=83, nozzle_temp=220, bed_temp=65, filament="PLA Basic",
                           filament_color="161616FF")
    SAMPLE_STATES = (State.PRINTING, State.PAUSED, State.FINISHED, State.FAILED, State.IDLE)
    SAMPLE_ELAPSED_MIN = 61

    def _segmented(self, master: Any, values: list[str], command) -> ctk.CTkSegmentedButton:
        return ctk.CTkSegmentedButton(master, values=values, font=font(12), height=30, corner_radius=10,
                                      fg_color=SURFACE_2, selected_color=SURFACE_3,
                                      selected_hover_color=BORDER_HOVER, unselected_color=SURFACE_2,
                                      unselected_hover_color=SURFACE_3, text_color=TEXT, command=command)

    def _choice_row(self, master: Any, row: int, title: str, desc: str, options: dict[Any, str], value: Any,
                    divider: bool = True) -> Callable[[], Any]:
        """A setting row with a segmented choice; returns a getter of the chosen option."""
        r = SettingRow(master, title, desc, divider=divider, wrap=420)
        r.grid(row=row, column=0, sticky="ew")
        seg = r.place_below(self._segmented(r, list(options.values()), lambda _v: self._on_display_change()))
        seg.set(options.get(value, next(iter(options.values()))))
        self.cons_choices.append(seg)
        return lambda: next((k for k, v in options.items() if v == seg.get()), next(iter(options)))

    def _build_constructor(self, page: ctk.CTkFrame) -> None:
        actions = self._page_header(page, "presence", tr("page.constructor"))
        self.cons_reset = ghost_button(actions, tr("cons.reset"), self.images.icon("reset", TEXT_2, 15),
                                       self._reset_templates)
        self.cons_reset.grid(row=0, column=0)
        self.cons = custom_options(self.cfg.get("presence"))
        self.cons_choices: list[ctk.CTkSegmentedButton] = []
        self.edit_state = "all"

        wrap = ctk.CTkFrame(page, fg_color="transparent")
        wrap.grid(row=1, column=0, sticky="nsew", padx=(20, 12), pady=(0, 16))
        wrap.grid_columnconfigure(0, weight=3, uniform="cons")
        wrap.grid_columnconfigure(1, weight=2, uniform="cons")
        wrap.grid_rowconfigure(0, weight=1)

        # Left: the editor (scrolls)
        body = ctk.CTkScrollableFrame(wrap, fg_color="transparent")
        body.grid(row=0, column=0, sticky="nsew")
        body.grid_columnconfigure(0, weight=1)

        # Lines
        top = self._section(body, 0, tr("cons.lines"))
        r = SettingRow(top, tr("cons.custom"), tr("desc.cons_custom"), divider=False, wrap=380)
        r.grid(row=0, column=0, sticky="ew")
        self.custom_on = self._switch(r, bool(self.cons["enabled"]), self._on_custom_toggle)
        r = SettingRow(top, tr("cons.text_for"), tr("desc.cons_text_for"), wrap=420)
        r.grid(row=1, column=0, sticky="ew")
        self.edit_names = {"all": tr("cons.all"), **{st.value: tr(f"sample.{st.value}") for st in self.SAMPLE_STATES}}
        self.cons_edit = r.place_below(self._segmented(r, list(self.edit_names.values()), self._on_edit_state))
        self.cons_edit.set(self.edit_names["all"])
        self.override_row = SettingRow(top, tr("cons.own_state"), tr("desc.cons_own_state"), wrap=380)
        self.override_on = self._switch(self.override_row, False, self._on_override_toggle)
        hints = {"details": tr("desc.cons_details"), "state": "", "large_text": tr("cons.hover_hint"),
                 "small_text": tr("cons.hover_hint")}
        self.template_entries: dict[str, TemplateField] = {}
        for i, key in enumerate(TEMPLATE_KEYS):
            f = TemplateField(top, tr(f"cons.{key}"), hints[key], toggle=key in HIDEABLE)
            f.grid(row=3 + i, column=0, sticky="ew", pady=(6 if i == 0 else 12, 16 if i == 3 else 0))
            f.entry.bind("<KeyRelease>", lambda _e, k=key: self._on_template_edit(k), add="+")
            f.entry.bind("<FocusIn>", lambda _e, k=key: setattr(self, "focused_template", k), add="+")
            if f.shown is not None:
                f.shown.set(key not in self.cons["hidden"])
                f.switch.configure(command=self._on_display_change)
            self.template_entries[key] = f

        # How the status is shown
        dc = self._section(body, 2, tr("cons.display"))
        self.get_timer = self._choice_row(dc, 0, tr("cons.timer"), tr("desc.cons_timer"), {
            "remaining": tr("cons.timer_remaining"), "elapsed": tr("cons.timer_elapsed"),
            "none": tr("cons.none")}, self.cons["timer"], divider=False)
        self.get_party = self._choice_row(dc, 1, tr("cons.party_title"), tr("desc.cons_party"), {
            "none": tr("cons.none"), "layers": tr("cons.party_layers"), "progress": tr("cons.party_progress")},
            self.cons["party"])
        r = SettingRow(dc, tr("cons.badge"), tr("desc.cons_badge"), wrap=380)
        r.grid(row=2, column=0, sticky="ew")
        self.badge_on = self._switch(r, "small_image" not in self.cons["hidden"], self._on_display_change)
        self.badge_switch = r.winfo_children()[-1]
        self.get_type = self._choice_row(dc, 3, tr("cons.type"), tr("desc.cons_type"), {
            0: tr("type.playing"), 3: tr("type.watching"), 2: tr("type.listening"), 5: tr("type.competing")},
            self.cons["activity_type"])
        self.get_display = self._choice_row(dc, 4, tr("cons.member_list"), tr("desc.cons_member_list"), {
            "name": tr("cons.show_name"), "details": tr("cons.show_details"), "state": tr("cons.show_state")},
            self.cons["status_display"])

        # Own button
        bc = self._section(body, 4, tr("cons.button"))
        r = SettingRow(bc, tr("cons.button_on"), tr("desc.cons_button"), divider=False, wrap=380)
        r.grid(row=0, column=0, sticky="ew")
        self.button_on = self._switch(r, bool(self.cons["button_on"]), self._on_display_change)
        self.button_switch = r.winfo_children()[-1]
        self.f_button_label = TemplateField(bc, tr("cons.button_label"), tr("desc.cons_button_label"))
        self.f_button_label.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        self.f_button_label.set(str(self.cons["button_label"]))
        self.f_button_url = TemplateField(bc, tr("cons.button_url"), "")
        self.f_button_url.grid(row=2, column=0, sticky="ew", pady=(12, 16))
        self.f_button_url.set(str(self.cons["button_url"]))
        self.f_button_url.entry.configure(placeholder_text="https://makerworld.com/…")
        if not self.cons["button_url"]:
            getattr(self.f_button_url.entry, "_activate_placeholder", lambda: None)()
        for f, key in ((self.f_button_label, "button_label"), (self.f_button_url, "button_url")):
            f.entry.bind("<KeyRelease>", lambda _e, k=key, fld=f: self._on_button_edit(k, fld), add="+")
        self.f_button_label.entry.bind("<FocusIn>", lambda _e: setattr(self, "focused_template", "button_label"),
                                       add="+")

        # Variables
        vc = self._section(body, 6, tr("cons.vars"))
        ctk.CTkLabel(vc, text=tr("cons.vars_hint"), font=font(12), text_color=MUTED, anchor="w", justify="left",
                     wraplength=430).grid(row=0, column=0, sticky="w", pady=(10, 8))
        chips = ctk.CTkFrame(vc, fg_color="transparent")
        chips.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        self.var_chips: list[ctk.CTkButton] = []
        for i, var in enumerate(VARIABLES):
            chip = ctk.CTkButton(chips, text=tr(f"var.{var}"), height=30, corner_radius=8, font=font(12),
                                 fg_color=SURFACE_2, hover_color=SURFACE_3, border_width=1, border_color=BORDER,
                                 text_color=TEXT_2, width=10, command=lambda v=var: self._insert_variable(v))
            chip.grid(row=i // 4, column=i % 4, sticky="ew", padx=(0, 6), pady=3)
            self.var_chips.append(chip)
        chips.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="chips")

        # Right: live preview (stays in place while the editor scrolls)
        side = Surface(wrap)
        side.grid(row=0, column=1, sticky="new", padx=(12, 12))
        inner = ctk.CTkFrame(side, fg_color="transparent")
        inner.grid(row=0, column=0, sticky="ew", padx=20, pady=20)
        inner.grid_columnconfigure(0, weight=1)
        section_label(inner, tr("cons.preview")).grid(row=0, column=0, sticky="w")
        self.cons_live = ctk.CTkLabel(inner, text="", font=font(12, "bold"), anchor="w", justify="left",
                                      wraplength=270)
        self.cons_live.grid(row=1, column=0, sticky="w", pady=(4, 10))
        names = [tr("cons.now")] + [tr(f"sample.{st.value}") for st in self.SAMPLE_STATES]
        pick = ctk.CTkFrame(inner, fg_color="transparent")
        pick.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        pick.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(pick, text=tr("cons.preview_as"), font=font(12), text_color=MUTED).grid(
            row=0, column=0, padx=(0, 10))
        self.cons_sample = ctk.CTkOptionMenu(
            pick, values=names, font=font(12), dropdown_font=font(12), height=30, corner_radius=10,
            fg_color=SURFACE_2, button_color=SURFACE_3, button_hover_color=BORDER_HOVER, text_color=TEXT,
            dropdown_fg_color=SURFACE_2, dropdown_hover_color=SURFACE_3, dropdown_text_color=TEXT,
            command=lambda _v: self._show_constructor_preview())
        self.cons_sample.set(names[0])
        self.cons_sample.grid(row=0, column=1, sticky="ew")
        self.cons_card = DiscordCard(inner, self.images)
        self.cons_card.grid(row=3, column=0, sticky="ew")
        self.cons_hover = ctk.CTkLabel(inner, text="", font=font(12), text_color=MUTED, anchor="w", justify="left",
                                       wraplength=270)
        self.cons_hover.grid(row=4, column=0, sticky="w", pady=(12, 0))
        self.cons_source = ctk.CTkLabel(inner, text="", font=font(11), text_color=FAINT, anchor="w")
        self.cons_source.grid(row=5, column=0, sticky="w", pady=(6, 0))
        self._load_template_fields()

    # Constructor state

    def _custom_opts(self) -> dict[str, Any]:
        if not self.template_entries:
            return custom_options(self.cfg.get("presence"))
        c = self.cons
        c["enabled"] = self.custom_on.get()
        hidden = [k for k, f in self.template_entries.items() if f.shown is not None and not f.shown.get()]
        if not self.badge_on.get():
            hidden.append("small_image")
        c.update(hidden=hidden, timer=self.get_timer(), party=self.get_party(), activity_type=self.get_type(),
                 status_display=self.get_display(), button_on=self.button_on.get())
        return json.loads(json.dumps(c))

    def _template_target(self) -> dict[str, Any] | None:
        """Where the edited lines are stored: the main templates or the selected state's own ones."""
        if self.edit_state == "all":
            return self.cons
        return self.cons["overrides"].get(self.edit_state)

    def _load_template_fields(self) -> None:
        own = self.edit_state != "all" and self.edit_state in self.cons["overrides"]
        if self.edit_state == "all":
            self.override_row.grid_remove()
        else:
            self.override_row.grid(row=2, column=0, sticky="ew")
            self.override_on.set(own)
        source = self._template_target() or self.cons
        for key, f in self.template_entries.items():
            f.set(str(source.get(key, self.cons.get(key, ""))))
        self._update_template_state()

    def _update_template_state(self) -> None:
        on = self.custom_on.get()
        editable = on and (self.edit_state == "all" or self.edit_state in self.cons["overrides"])
        for f in self.template_entries.values():
            f.enable(editable, toggle=on)
        if not self.badge_on.get():
            self.template_entries["small_text"].enable(editable, toggle=False)
        for chip in self.var_chips:
            chip.configure(state="normal" if on else "disabled")
        for w in (self.cons_reset, self.cons_edit, self.badge_switch, self.button_switch, *self.cons_choices):
            w.configure(state="normal" if on else "disabled")
        self.override_row.winfo_children()[-1].configure(state="normal" if on else "disabled")
        button = on and self.button_on.get()
        self.f_button_label.enable(button)
        self.f_button_url.enable(button)

    def _on_custom_toggle(self) -> None:
        self._update_template_state()
        self._presence_changed()

    def _on_edit_state(self, value: str) -> None:
        self.edit_state = next((k for k, v in self.edit_names.items() if v == value), "all")
        if self.edit_state != "all":
            self.cons_sample.set(value)  # preview the state being edited
        self._load_template_fields()
        self._show_constructor_preview()

    def _on_override_toggle(self) -> None:
        if self.override_on.get():
            self.cons["overrides"][self.edit_state] = {k: self.cons[k] for k in TEMPLATE_KEYS}
        else:
            self.cons["overrides"].pop(self.edit_state, None)
        self._load_template_fields()
        self._presence_changed()

    def _on_template_edit(self, key: str) -> None:
        target = self._template_target()
        if target is not None:
            target[key] = self.template_entries[key].get()
        self._presence_changed()

    def _on_button_edit(self, key: str, field: TemplateField) -> None:
        self.cons[key] = field.get().strip()
        self._presence_changed()

    def _on_display_change(self) -> None:
        self._update_template_state()
        self._presence_changed()

    def _insert_variable(self, var: str) -> None:
        if self.focused_template == "button_label":
            field = self.f_button_label
        else:
            field = self.template_entries[self.focused_template]
        if field.entry.cget("state") == "disabled":
            return
        field.entry.insert("insert", "{" + var + "}")
        field.entry.focus_set()
        if self.focused_template == "button_label":
            self._on_button_edit("button_label", field)
        else:
            self._on_template_edit(self.focused_template)

    def _reset_templates(self) -> None:
        """Back to the defaults for the lines being edited (or everything when editing all states)."""
        if self.edit_state == "all":
            enabled = self.custom_on.get()
            self.cons = custom_options({})
            self.cons["enabled"] = enabled
            for f in self.template_entries.values():
                if f.shown is not None:
                    f.shown.set(True)
            self.badge_on.set(True)
            self.button_on.set(False)
            self.f_button_label.set("")
            self.f_button_url.set("")
            for seg, value in zip(self.cons_choices, (tr("cons.timer_remaining"), tr("cons.none"),
                                                      tr("type.playing"), tr("cons.show_name"))):
                seg.set(value)
        else:
            self.cons["overrides"].pop(self.edit_state, None)
        self._load_template_fields()
        self._presence_changed()

    # Constructor preview

    def _preview_source(self) -> tuple[dict[str, Any], PrinterStatus, float | None, bool]:
        """Printer, status and print start for the preview; the bool says whether it is real data."""
        printers = self._shown_printers()
        printer = printers[0] if printers else self.printers[self.sel]
        sample_start = time.time() - self.SAMPLE_ELAPSED_MIN * 60
        choice = self.cons_sample.get()
        if choice == tr("cons.now"):
            if self._running() and self.statuses and self.featured < len(printers):
                start = self.clocks[self.featured].start if self.featured < len(self.clocks) else None
                return printers[self.featured], self.statuses[self.featured], start, True
            return printer, self.SAMPLE, sample_start, False
        state = next((st for st in self.SAMPLE_STATES if tr(f"sample.{st.value}") == choice), State.PRINTING)
        if state in (State.PRINTING, State.PAUSED):
            return printer, dataclasses.replace(self.SAMPLE, state=state), sample_start, False
        if state in (State.FINISHED, State.FAILED):
            done = state == State.FINISHED
            return printer, dataclasses.replace(self.SAMPLE, state=state, progress=100 if done else 42,
                                                layer=240 if done else 87, remaining_min=0, nozzle_temp=48,
                                                bed_temp=40), None, False
        return printer, PrinterStatus(state=State.IDLE, nozzle_temp=27, bed_temp=25, filament="PLA Basic",
                                      filament_color="161616FF"), None, False

    def _show_constructor_preview(self) -> None:
        if not hasattr(self, "cons_card") or not self.template_entries:
            return
        p, s, start, real = self._preview_source()
        activity = self._activity(s, printer_name(p), start)
        empty = tr("home.hidden") if s.state == State.OFFLINE else tr("strip.off")
        self.cons_card.show(printer_name(p), printer_image(p), activity, s.remaining_min, empty,
                            self.show_button.get())
        hover = []
        if activity and activity.get("large_text"):
            hover.append(tr("cons.hover_large", text=activity["large_text"].strip()))
        if activity and activity.get("small_text"):
            hover.append(tr("cons.hover_small", text=activity["small_text"].strip()))
        if activity:
            shown = {"details": activity["details"], "state": activity.get("state", "")}.get(
                activity.get("status_display_type", ""), "") or tr("cons.app_name")
            hover.append(tr("cons.member_line", text=f"{self.cons_card.header.cget('text').capitalize()} "
                                                     f"{shown.strip()}"))
        self.cons_source.configure(text="" if real else tr("cons.sample"))
        self.cons_hover.configure(text="\n".join(hover))
        self._update_counters(p, s)
        if not self._push_job:
            self.cons_live.configure(text=tr("cons.live_on") if self._running() else tr("cons.live_off"),
                                     text_color=GREEN if self._running() else MUTED)

    def _update_counters(self, p: dict[str, Any], s: PrinterStatus) -> None:
        lines = render_lines(s, printer_name(p), self._lang_code(), self._custom_opts(), hide_job=self.hide_job.get())
        for key, f in self.template_entries.items():
            f.count(len(lines[key]), 128)
        label = lines["button_label"].strip()
        self.f_button_label.count(len(label.encode("utf-8")), BUTTON_LIMIT, " B")
        url = self.f_button_url.get().strip()
        bad_url = bool(url) and not valid_url(url)
        self.f_button_url.hint.configure(text=tr("cons.bad_url") if bad_url else tr("desc.cons_button_url"),
                                         text_color=AMBER if bad_url else FAINT)

    def _presence_changed(self) -> None:
        """Any status option changed: redraw previews now, send to Discord after a short pause in typing."""
        self._refresh_view()
        if self._push_job:
            self.root.after_cancel(self._push_job)
        self._push_job = self.root.after(600, self._push_presence)

    def _push_presence(self) -> None:
        self._push_job = None
        cfg = self._collect()
        settings.save(cfg)
        if self._running() and self.runner:
            self.runner.update_presence(cfg)
            self.cons_live.configure(text=tr("cons.sent"), text_color=GREEN)
            self.root.after(2500, self._show_constructor_preview)

    # Settings page ---------------------------------------------------------

    def _switch(self, row: SettingRow, value: bool, command=None) -> tk.BooleanVar:
        var = tk.BooleanVar(value=value)
        row.place_control(ctk.CTkSwitch(row, text="", variable=var, width=46, switch_width=42, switch_height=22,
                                        progress_color=GREEN, button_color="#ffffff",
                                        button_hover_color="#e6e6e6", fg_color=SURFACE_3, command=command))
        return var

    def _section(self, body: Any, row: int, title: str) -> ctk.CTkFrame:
        section_label(body, title).grid(row=row, column=0, sticky="w", padx=14, pady=(0, 8))
        card = Surface(body)
        card.grid(row=row + 1, column=0, sticky="ew", padx=12, pady=(0, 26))
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.grid(row=0, column=0, sticky="ew", padx=22, pady=6)
        inner.grid_columnconfigure(0, weight=1)
        return inner

    def _build_settings(self, page: ctk.CTkFrame) -> None:
        self._page_header(page, "settings", tr("page.settings"))
        body = ctk.CTkScrollableFrame(page, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=(20, 12), pady=(0, 16))
        body.grid_columnconfigure(0, weight=1)
        d, pr, app = self.cfg["discord"], self.cfg["presence"], self.cfg["app"]

        # Printers
        section_label(body, tr("set.printers")).grid(row=0, column=0, sticky="w", padx=14, pady=(0, 8))
        card = Surface(body)
        card.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 26))
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=22, pady=(18, 8))
        top.grid_columnconfigure(0, weight=1)
        self.find_info = ctk.CTkLabel(top, text="", font=font(12), text_color=MUTED, anchor="w", justify="left",
                                      wraplength=420)
        self.find_info.grid(row=0, column=0, sticky="w")
        self.find_btn = ghost_button(top, tr("set.find").replace("🔍", "").strip(),
                                     self.images.icon("search", TEXT_2, 15), self.search)
        self.find_btn.grid(row=0, column=1, padx=(8, 8))
        self.add_btn = ghost_button(top, tr("set.add_printer").replace("+", "").strip(),
                                    self.images.icon("plus", TEXT_2, 15), self._add_printer)
        self.add_btn.grid(row=0, column=2)
        self.printer_list = ctk.CTkFrame(card, fg_color="transparent")
        self.printer_list.grid(row=1, column=0, sticky="ew", padx=14)
        self.printer_list.grid_columnconfigure(0, weight=1)

        editor = ctk.CTkFrame(card, fg_color=BG, corner_radius=14, border_width=1, border_color=BORDER)
        editor.grid(row=2, column=0, sticky="ew", padx=22, pady=(10, 22))
        editor.grid_columnconfigure((0, 1), weight=1, uniform="f")
        head = ctk.CTkFrame(editor, fg_color="transparent")
        head.grid(row=0, column=0, columnspan=2, sticky="ew", padx=20, pady=(16, 6))
        head.grid_columnconfigure(0, weight=1)
        self.editor_title = ctk.CTkLabel(head, text="", font=font(15, "bold"), text_color=TEXT, anchor="w")
        self.editor_title.grid(row=0, column=0, sticky="w")
        self.remove_btn = ghost_button(head, tr("set.remove_printer"), self.images.icon("trash", "#ff9a9e", 15),
                                       self._remove_printer, danger=True)
        self.remove_btn.grid(row=0, column=1)
        self.f_host = Field(editor, tr("set.host"), tr("set.host_hint"), placeholder="192.168.1.50")
        self.f_serial = Field(editor, tr("set.serial"), tr("set.serial_hint"))
        self.f_code = Field(editor, "Access Code", tr("set.code_hint"), secret=True,
                            placeholder=tr("set.code_placeholder"))
        self.f_name = Field(editor, tr("set.name"), tr("set.name_hint"))
        self.fields = (self.f_host, self.f_serial, self.f_code, self.f_name)
        for i, f in enumerate(self.fields):
            f.grid(row=1 + i // 2, column=i % 2, sticky="new", padx=(20 if i % 2 == 0 else 10, 10 if i % 2 == 0 else 20),
                   pady=(8, 18 if i >= 2 else 4))
        self.printer_rows: list[ctk.CTkFrame] = []
        self._load_fields()

        # Discord
        dc = self._section(body, 2, "Discord")
        row = SettingRow(dc, tr("set.default_app"), tr("desc.default_app"), divider=False)
        row.grid(row=0, column=0, sticky="ew")
        custom = str(d.get("client_id", ""))
        self.use_default = self._switch(row, bool(d.get("use_default", not custom)), self._update_client_state)
        self.client_box = ctk.CTkFrame(dc, fg_color="transparent")
        self.client_box.grid_columnconfigure(0, weight=1)
        self.f_client = Field(self.client_box, tr("set.client_id"), tr("set.client_id_hint"), custom)
        self.f_client.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(self.client_box, text=tr("set.custom_app_help"), height=26, fg_color="transparent",
                      hover_color=SURFACE_2, text_color=LINK, font=font(12), anchor="w", width=10,
                      command=lambda: webbrowser.open(docs_url(custom_app=True))).grid(
            row=1, column=0, sticky="w", pady=(4, 12))
        for i, (key, title, default, cmd) in enumerate((
                ("button", "set.button", True, self._presence_changed),
                ("hide_job", "set.hide_job", False, self._presence_changed),
                ("show_when_idle", "set.show_idle", True, self._presence_changed)), start=2):
            desc = {"button": "desc.button", "hide_job": "desc.hide_job", "show_when_idle": "desc.show_idle"}[key]
            r = SettingRow(dc, tr(title), tr(desc))
            r.grid(row=i, column=0, sticky="ew")
            var = self._switch(r, bool(pr.get(key, default)), cmd)
            setattr(self, {"button": "show_button", "hide_job": "hide_job", "show_when_idle": "show_idle"}[key], var)

        # Behaviour
        bc = self._section(body, 4, tr("set.behaviour"))
        rows: list[tuple[str, str, str, bool, Any]] = []
        if winstartup.supported():
            rows.append(("launch_windows", "set.launch_windows", "desc.launch_windows", winstartup.is_enabled(),
                         self._on_launch_windows))
        if self.tray.available:
            rows.append(("close_to_tray", "set.close_to_tray", "desc.close_to_tray",
                         bool(app.get("close_to_tray", True)), None))
        rows.append(("autostart", "set.autostart", "desc.autostart", bool(app.get("autostart", False)), None))
        rows.append(("check_updates", "set.check_updates", "desc.check_updates",
                     bool(app.get("check_updates", True)), None))
        for i, (attr, title, desc, value, cmd) in enumerate(rows):
            r = SettingRow(bc, tr(title), tr(desc), divider=i > 0)
            r.grid(row=i, column=0, sticky="ew")
            setattr(self, attr, self._switch(r, value, cmd))

        # Language
        lc = self._section(body, 6, tr("sec.language"))
        r = SettingRow(lc, tr("set.ui_lang"), tr("desc.ui_lang"), divider=False)
        r.grid(row=0, column=0, sticky="ew")
        self.ui_lang = r.place_control(self._lang_selector(r, app.get("language", "auto"), self._on_ui_lang))
        r = SettingRow(lc, tr("set.status_lang"), tr("desc.status_lang"))
        r.grid(row=1, column=0, sticky="ew")
        self.lang = r.place_control(self._lang_selector(r, pr.get("language", "auto"),
                                                        lambda _: self._presence_changed()))
        self._update_client_state()

    def _lang_selector(self, master: Any, value: str, command) -> ctk.CTkSegmentedButton:
        names = [tr("lang.auto"), *LANGUAGE_NAMES.values()]
        seg = ctk.CTkSegmentedButton(master, values=names, font=font(12), height=32, corner_radius=10,
                                     fg_color=SURFACE_2, selected_color=SURFACE_3,
                                     selected_hover_color=BORDER_HOVER, unselected_color=SURFACE_2,
                                     unselected_hover_color=SURFACE_3, text_color=TEXT, command=command)
        seg.set(LANGUAGE_NAMES.get(value, tr("lang.auto")))
        return seg

    @staticmethod
    def _lang_choice(seg: ctk.CTkSegmentedButton) -> str:
        return {name: code for code, name in LANGUAGE_NAMES.items()}.get(seg.get(), "auto")

    def _lang_code(self) -> str:
        # "Auto" status language follows the interface language.
        return status_language(self._lang_choice(self.lang), self._lang_choice(self.ui_lang))

    # Printer list (settings) -----------------------------------------------

    def _render_printer_rows(self) -> None:
        for row in self.printer_rows:
            row.destroy()
        self.printer_rows = []
        for i, p in enumerate(self.printers):
            selected = i == self.sel
            row = ctk.CTkFrame(self.printer_list, fg_color=SURFACE_2 if selected else "transparent",
                               corner_radius=12)
            row.grid(row=i, column=0, sticky="ew", pady=2)
            row.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(row, text="", image=self.images.photo(printer_image(p), 40)).grid(
                row=0, column=0, rowspan=2, padx=(10, 12), pady=8)
            name = tr("set.new_printer") if is_empty(p) else printer_name(p)
            ctk.CTkLabel(row, text=name, font=font(14, "bold"), text_color=TEXT, anchor="w", height=20).grid(
                row=0, column=1, sticky="sw", pady=(8, 0))
            sub = " · ".join(x for x in (p.get("host"), p.get("serial")) if x) or "—"
            ctk.CTkLabel(row, text=sub, font=font(12), text_color=MUTED, anchor="w", height=16).grid(
                row=1, column=1, sticky="nw", pady=(0, 8))
            ready = bool(p.get("host") and p.get("serial") and p.get("access_code"))
            ctk.CTkLabel(row, text=f"  {tr('chip.ready') if ready else tr('chip.need_code')}  ",
                         font=font(11, "bold"), corner_radius=8, height=24,
                         fg_color=GREEN_SOFT if ready else AMBER_SOFT,
                         text_color="#6fe3a0" if ready else AMBER).grid(row=0, column=2, rowspan=2, padx=8)
            ctk.CTkLabel(row, text="", image=self.images.icon("chevron", FAINT, 14)).grid(
                row=0, column=3, rowspan=2, padx=(0, 12))
            if not self._running():
                bind_click(row, lambda idx=i: self._pick(idx))
            self.printer_rows.append(row)
        p = self.printers[self.sel]
        self.editor_title.configure(text=f"{tr('sec.printer_edit')} · "
                                         f"{tr('set.new_printer') if is_empty(p) else printer_name(p)}")

    def _pick(self, index: int) -> None:
        if index == self.sel:
            return
        self._store_fields()
        self._select(index)

    def _store_fields(self) -> None:
        self.printers[self.sel].update(host=self.f_host.get(), serial=self.f_serial.get(),
                                       access_code=self.f_code.get(), name=self.f_name.get())

    def _load_fields(self) -> None:
        p = self.printers[self.sel]
        self.f_host.set(p.get("host", ""))
        self.f_serial.set(p.get("serial", ""))
        self.f_code.set(p.get("access_code", ""))
        self.f_name.entry.configure(placeholder_text=display_name(p.get("model_code"), p.get("serial")))
        self.f_name.set(p.get("name", ""))
        self._render_printer_rows()

    def _select(self, index: int) -> None:
        self.sel = max(0, min(index, len(self.printers) - 1))
        self._load_fields()
        if not self._running():
            self._refresh_view()

    def _add_printer(self) -> None:
        self._store_fields()
        self.printers.append(dict(settings.EMPTY_PRINTER))
        self._select(len(self.printers) - 1)
        self.f_host.entry.focus_set()

    def _remove_printer(self) -> None:
        if len(self.printers) > 1:
            self.printers.pop(self.sel)
            self._select(self.sel - 1 if self.sel else 0)
        else:
            self.printers[0] = dict(settings.EMPTY_PRINTER)
            self._select(0)
        settings.save(self._collect())

    # Log page ----------------------------------------------------------------

    def _build_log(self, page: ctk.CTkFrame) -> None:
        actions = self._page_header(page, "log", tr("page.log"))
        ghost_button(actions, tr("log.copy"), self.images.icon("copy", TEXT_2, 15), self._copy_log).grid(
            row=0, column=0, padx=(0, 8))
        ghost_button(actions, tr("log.folder"), self.images.icon("folder", TEXT_2, 15), self._open_folder).grid(
            row=0, column=1, padx=(0, 8))
        ghost_button(actions, tr("log.clear"), self.images.icon("trash", TEXT_2, 15), self._clear_log).grid(
            row=0, column=2)
        card = Surface(page)
        card.grid(row=1, column=0, sticky="nsew", padx=32, pady=(0, 28))
        card.grid_rowconfigure(0, weight=1)
        mono = "Cascadia Mono" if "Cascadia Mono" in tkfont.families() else "Consolas" \
            if "Consolas" in tkfont.families() else "DejaVu Sans Mono"
        self.log_box = ctk.CTkTextbox(card, fg_color="transparent", border_width=0, corner_radius=0,
                                      font=ctk.CTkFont(family=mono, size=12), text_color=TEXT_2, wrap="word",
                                      spacing1=3, spacing3=3)
        self.log_box.grid(row=0, column=0, sticky="nsew", padx=16, pady=14)
        box = self.log_box._textbox
        box.tag_config("time", foreground=FAINT)
        box.tag_config("warn", foreground=AMBER)
        box.tag_config("error", foreground="#ff8a8e")
        for level, line in self.log_lines:
            self._insert_log(level, line)
        self.log_box.configure(state="disabled")

    def _insert_log(self, level: int, line: str) -> None:
        time_part, _, msg = line.partition("  ")
        tag = "error" if level >= logging.ERROR else "warn" if level >= logging.WARNING else None
        self.log_box.insert("end", time_part + "   ", "time")
        self.log_box.insert("end", msg + "\n", tag)

    def _append_log(self, level: int, line: str) -> None:
        self.log_lines.append((level, line))
        if len(self.log_lines) > 500:
            self.log_lines = self.log_lines[-400:]
        self.log_box.configure(state="normal")
        self._insert_log(level, line)
        if int(self.log_box.index("end-1c").split(".")[0]) > 500:
            self.log_box.delete("1.0", "100.0")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _copy_log(self) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append("\n".join(line for _, line in self.log_lines))

    def _clear_log(self) -> None:
        self.log_lines = []
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    def _open_folder(self) -> None:
        folder = settings.settings_path().parent
        folder.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(folder)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open" if sys.platform != "darwin" else "open", str(folder)])

    # About page ----------------------------------------------------------------

    def _build_about(self, page: ctk.CTkFrame) -> None:
        self._page_header(page, "about", tr("page.about"))
        card = Surface(page)
        card.grid(row=1, column=0, sticky="new", padx=32)
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.grid(row=0, column=0, sticky="ew", padx=32, pady=32)
        inner.grid_columnconfigure(1, weight=1)
        self._about_logo = ctk.CTkImage(self._app_icon(), size=(88, 88))
        ctk.CTkLabel(inner, text="", image=self._about_logo).grid(row=0, column=0, rowspan=3, padx=(0, 24),
                                                                  sticky="n")
        ctk.CTkLabel(inner, text="Print Presence", font=font(26, "bold"), text_color=TEXT, anchor="w").grid(
            row=0, column=1, sticky="w")
        ctk.CTkLabel(inner, text=f"v{__version__}" + (" · Portable" if settings.is_portable() else ""),
                     font=font(13), text_color=MUTED, anchor="w").grid(
            row=1, column=1, sticky="w")
        ctk.CTkLabel(inner, text=tr("about.desc"), font=font(14), text_color=TEXT_2, anchor="w", justify="left",
                     wraplength=560).grid(row=2, column=1, sticky="w", pady=(12, 0))
        buttons = ctk.CTkFrame(inner, fg_color="transparent")
        buttons.grid(row=3, column=1, sticky="w", pady=(24, 0))
        ctk.CTkButton(buttons, text=tr("about.github"), height=38, corner_radius=10, font=font(13, "bold"),
                      fg_color=GREEN, hover_color=GREEN_HOVER, command=lambda: webbrowser.open(REPO_URL)).grid(
            row=0, column=0, padx=(0, 8))
        ghost_button(buttons, tr("about.check"), self.images.icon("arrow_up", TEXT_2, 15),
                     self._about_check).grid(row=0, column=1, padx=(0, 8))
        ghost_button(buttons, tr("about.bug"), None,
                     lambda: webbrowser.open(REPO_URL + "/issues/new/choose")).grid(row=0, column=2, padx=(0, 8))
        ghost_button(buttons, tr("set.instructions").replace("→", "").strip(), None,
                     lambda: webbrowser.open(docs_url())).grid(row=0, column=3)
        self.about_status = ctk.CTkLabel(inner, text="", font=font(12), text_color=MUTED, anchor="w")
        self.about_status.grid(row=4, column=1, sticky="w", pady=(10, 0))
        ctk.CTkLabel(page, text=tr("about.legal"), font=font(11), text_color=FAINT).grid(
            row=2, column=0, sticky="w", padx=36, pady=(14, 24))

    def _about_check(self) -> None:
        self.about_status.configure(text=tr("about.checking"), text_color=MUTED)
        self._check_updates(manual=True)

    def _check_updates(self, manual: bool = False) -> None:
        threading.Thread(target=lambda: self.events.put(("update", (updates.check(), manual))), daemon=True).start()

    # Helpers ---------------------------------------------------------------

    def _update_client_state(self) -> None:
        if self.use_default.get():
            self.client_box.grid_remove()
        else:
            self.client_box.grid(row=1, column=0, sticky="ew", pady=(0, 4))
        self.f_client.enable(not self.use_default.get() and not self._running())

    def _set_inputs_enabled(self, on: bool) -> None:
        for f in self.fields:
            f.enable(on)
        state = "normal" if on else "disabled"
        for w in (self.find_btn, self.add_btn, self.remove_btn, self.dash_find, self.dash_add):
            w.configure(state=state)
        self._render_printer_rows()
        self._update_client_state()

    def _collect(self) -> dict[str, Any]:
        self._store_fields()
        cfg = self.cfg
        cfg["printers"] = [dict(p) for p in self.printers if not is_empty(p)]
        cfg.setdefault("discord", {}).update(use_default=self.use_default.get(), client_id=self.f_client.get())
        cfg["presence"].update(show_when_idle=self.show_idle.get(), language=self._lang_choice(self.lang),
                               hide_job=self.hide_job.get(), button=self.show_button.get(),
                               custom=self._custom_opts())
        cfg["app"].update(autostart=self.autostart.get(), language=self._lang_choice(self.ui_lang),
                          check_updates=self.check_updates.get())
        if hasattr(self, "close_to_tray"):
            cfg["app"]["close_to_tray"] = self.close_to_tray.get()
        return cfg

    def _set_pill(self, text: str, color: str) -> None:
        self.pill_dot.configure(text_color=color)
        self.pill.configure(text=text, text_color=TEXT_2 if color == MUTED else color)

    def _update_button(self) -> None:
        if self._running():
            self.button.configure(text=f"  {tr('btn.stop').strip('■ ').strip()}", fg_color=RED, hover_color=RED_HOVER,
                                  image=self.images.icon("stop", "#ffffff", 14), state="normal")
        else:
            self.button.configure(text=f"  {tr('btn.start').strip('▶ ').strip()}", fg_color=GREEN,
                                  hover_color=GREEN_HOVER, image=self.images.icon("play", "#ffffff", 14),
                                  state="normal")
            self._set_pill(tr("pill.stopped"), MUTED)

    def _on_launch_windows(self) -> None:
        try:
            winstartup.set_enabled(self.launch_windows.get())
        except OSError as e:
            log.warning("%s", e)
            self.launch_windows.set(winstartup.is_enabled())

    def _show_update(self, info: tuple[str, str]) -> None:
        self.update_info = info
        self.update_btn.configure(text=f"  {tr('update.available', version=info[0]).replace('⬆', '').strip()}")
        self.update_btn.grid(row=0, column=0, sticky="ew", pady=(0, 10))

    def _on_ui_lang(self, _value: str) -> None:
        """Rebuild the window (and the tray menu) in the newly chosen language."""
        cfg = self._collect()
        settings.save(cfg)
        i18n.set_language(cfg["app"]["language"])
        for child in self.root.winfo_children():
            child.destroy()
        self.tray.stop()
        self.tray = Tray(self._app_icon(), self.events, self._running)
        self.page = "settings"
        self._build()
        if self._running():
            self._set_inputs_enabled(False)
            if self.statuses:
                self._on_status(self.statuses, self.featured, self.discord_ok)
            else:
                self._set_pill(tr("pill.connecting"), AMBER)
        self._refresh_view()

    # Discovery -------------------------------------------------------------

    def search(self) -> None:
        if self.searching or self._running():
            return
        self.searching = True
        self.find_btn.configure(state="disabled", text=tr("set.searching").replace("🔍", "").strip())
        self.find_info.configure(text=tr("set.listening"), text_color=MUTED)
        threading.Thread(target=lambda: self.events.put(("found", discover(8.0))), daemon=True).start()

    def _on_found(self, found: list[FoundPrinter]) -> None:
        self.searching = False
        self.find_btn.configure(state="disabled" if self._running() else "normal",
                                text=tr("set.find").replace("🔍", "").strip())
        if not found:
            self.find_info.configure(text=tr("set.not_found"), text_color=AMBER)
            return
        if self._running():  # don't touch the settings of running printers
            self.find_info.configure(text=tr("set.found", n=len(found), added=0), text_color=GREEN)
            return
        self._store_fields()
        added, first_new = 0, None
        for f in found:
            log.info(tr("log.selected", title=f.title))
            idx = next((i for i, p in enumerate(self.printers) if p.get("serial") == f.serial), None)
            if idx is None:
                idx = next((i for i, p in enumerate(self.printers) if is_empty(p)), None)
                if idx is None:
                    self.printers.append(dict(settings.EMPTY_PRINTER))
                    idx = len(self.printers) - 1
                added += 1
            self.printers[idx].update(host=f.host, serial=f.serial, model_code=f.model_code)
            if first_new is None and not self.printers[idx].get("access_code"):
                first_new = idx
        self.find_info.configure(text=tr("set.found", n=len(found), added=added), text_color=GREEN)
        self._select(first_new if first_new is not None else self.sel)
        if first_new is not None:
            self.show_page("settings")
            self.f_code.entry.focus_set()

    # Start / stop ----------------------------------------------------------

    def toggle(self) -> None:
        if self._running():
            self.stop()
        else:
            self.start()

    def start(self) -> None:
        cfg = self._collect()
        settings.save(cfg)
        try:
            validate(cfg)
        except ValueError as e:
            self.show_page("settings")
            self._set_pill(tr("pill.fill_settings"), AMBER)
            self.find_info.configure(text=str(e), text_color=AMBER)
            log.warning("%s", e)
            if self.root.state() == "withdrawn":
                self.show_window()
            return
        self.art.use_app(client_id_from(cfg))
        self.run_printers = [dict(p) for p in cfg["printers"]]
        self.statuses = []
        self.clocks = []
        self.featured = 0
        self.runner = Runner(cfg, on_status=lambda s, f, d: self.events.put(("status", (s, f, d))))
        self.runner.start()
        self._set_inputs_enabled(False)
        self._update_button()
        self._set_pill(tr("pill.connecting"), AMBER)
        self.show_page("printers")
        self._refresh_view()
        log.info(tr("log.started"))

    def stop(self) -> None:
        if self.runner:
            self.runner.stop(timeout=0)
        self.button.configure(text=f"  {tr('btn.stopping')}", state="disabled")

    def show_window(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def on_close(self) -> None:
        if self.tray.available and getattr(self, "close_to_tray", None) is not None and self.close_to_tray.get():
            settings.save(self._collect())
            self.root.withdraw()
        else:
            self.quit()

    def quit(self) -> None:
        settings.save(self._collect())
        if self.runner:
            self.runner.stop(timeout=3)
        self.tray.stop()
        self.root.destroy()

    # Live updates ----------------------------------------------------------

    def _on_status(self, statuses: list[PrinterStatus], featured: int, discord_ok: bool) -> None:
        if not self._running() or not statuses:
            return
        self.statuses, self.featured, self.discord_ok = statuses, featured, discord_ok
        while len(self.clocks) < len(statuses):
            self.clocks.append(PrintClock())
        for clock, st in zip(self.clocks, statuses):
            clock.update(st)
        self._refresh_view()
        status = statuses[featured]
        if status.state == State.OFFLINE:
            self._set_pill(tr("pill.no_printer"), AMBER)
        elif not discord_ok:
            self._set_pill(tr("pill.no_discord"), AMBER)
        else:
            self._set_pill(tr("pill.running"), GREEN)
        self.tray.set_tooltip(f"Print Presence — {self.status_line}")

    def _on_tray(self, action: str) -> None:
        if action == "open":
            self.show_window()
        elif action == "toggle":
            self.toggle()
        elif action == "quit":
            self.quit()

    def _on_update(self, info: tuple[str, str] | None, manual: bool) -> None:
        if info:
            log.info(tr("log.update", version=info[0]))
            self._show_update(info)
        if manual:
            self.about_status.configure(
                text=tr("update.available", version=info[0]).replace("⬆", "").strip() if info else tr("about.latest"),
                text_color=GREEN if info else MUTED)

    def _poll(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "log":
                    self._append_log(*payload)
                elif kind == "status":
                    self._on_status(*payload)
                elif kind == "found":
                    self._on_found(payload)
                elif kind == "art":
                    self.images.clear()
                    self._refresh_view()
                    self._render_printer_rows()
                elif kind == "update":
                    self._on_update(*payload)
                elif kind == "tray":
                    self._on_tray(payload)
                    if payload == "quit":
                        return
        except queue.Empty:
            pass
        except tk.TclError:
            return  # window destroyed
        if self.runner and not self.runner.running:
            self.runner = None
            self.statuses = []
            self._update_button()
            self._set_inputs_enabled(True)
            self._refresh_view()
            self.tray.set_tooltip("Print Presence")
        self.root.after(200, self._poll)


def main() -> None:
    i18n.set_language(settings.load()["app"].get("language", "auto"))
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("green")
    root = ctk.CTk()
    App(root, minimized="--minimized" in sys.argv[1:])
    root.mainloop()
    # Settings are saved in App.quit(); the tray backend may leave a non-daemon thread
    # behind, so end the process explicitly instead of hanging in the background.
    logging.shutdown()
    os._exit(0)


if __name__ == "__main__":
    main()
