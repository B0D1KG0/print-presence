"""Print Presence desktop window (CustomTkinter): a dashboard of printer cards."""

from __future__ import annotations

import logging
import os
import queue
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

import customtkinter as ctk
from PIL import Image, ImageDraw

from . import __version__, i18n, settings, updates, winstartup
from .filament import filament_label
from .i18n import LANGUAGE_NAMES, tr
from .images import PrinterArt, ring
from .presence import build_activity, client_id_from
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

FONT = "Segoe UI"
BG = "#0d0f14"
CARD = "#151821"
CARD_2 = "#1c2030"
BORDER = "#222736"
TRACK = "#252a3a"
TEXT = "#e8eaee"
MUTED = "#7a8396"
GREEN = "#00ae42"
GREEN_HOVER = "#00953a"
RED = "#e5484d"
RED_HOVER = "#c93b40"
AMBER = "#f5a623"
BLUE = "#2ea0ff"
LINK = "#7aa2ff"
BLURPLE = "#5865f2"
STRIP = "#1b1d3a"
STRIP_BORDER = "#262b45"

STATE_COLORS = {
    State.OFFLINE: MUTED,
    State.IDLE: MUTED,
    State.PREPARING: BLUE,
    State.PRINTING: GREEN,
    State.PAUSED: AMBER,
    State.FINISHED: BLUE,
    State.FAILED: RED,
}


def docs_url(custom_app: bool = False) -> str:
    return DOCS.get(i18n.current(), DOCS["en"])[1 if custom_app else 0]


def resource(name: str) -> Path:
    # Files bundled by PyInstaller live in sys._MEIPASS.
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / name


def font(size: int = 13, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(family=FONT, size=size, weight=weight)


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


def bind_click(widget: tk.Misc, command: Callable[[], None]) -> None:
    widget.bind("<Button-1>", lambda _e: command(), add="+")
    try:
        widget.configure(cursor="hand2")
    except (tk.TclError, ValueError):
        pass
    for child in widget.winfo_children():
        bind_click(child, command)


class QueueHandler(logging.Handler):
    def __init__(self, q: queue.Queue) -> None:
        super().__init__()
        self.q = q
        self.setFormatter(logging.Formatter("%(asctime)s  %(message)s", "%H:%M:%S"))

    def emit(self, record: logging.LogRecord) -> None:
        self.q.put(("log", self.format(record)))


class Images:
    """CTkImage cache on top of PrinterArt (photos) and the status badges."""

    def __init__(self, art: PrinterArt) -> None:
        self.art = art
        self.cache: dict[tuple, ctk.CTkImage] = {}

    def clear(self) -> None:
        self.cache.clear()

    def photo(self, key: str, size: int) -> ctk.CTkImage:
        k = ("photo", key, size)
        if k not in self.cache:
            self.cache[k] = ctk.CTkImage(self.art.photo(key), size=(size, size))
        return self.cache[k]

    def preview(self, key: str, badge: str | None, size: int = 60) -> ctk.CTkImage:
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
                ImageDraw.Draw(circle).ellipse((0, 0, 115, 115), fill=STRIP)
                circle.paste(small, (10, 10), small)
                img.paste(circle, (big + pad - 116, big + pad - 116), circle)
            self.cache[k] = ctk.CTkImage(img, size=(size, size))
        return self.cache[k]

    def ring(self, percent: float | None, color: str, size: int = 96) -> ctk.CTkImage:
        k = ("ring", round(percent or 0), color, size)
        if k not in self.cache:
            self.cache[k] = ctk.CTkImage(ring(percent, color, TRACK, size=size), size=(size, size))
        return self.cache[k]


class Card(ctk.CTkFrame):
    def __init__(self, master: Any, title: str | None = None) -> None:
        super().__init__(master, fg_color=CARD, border_color=BORDER, corner_radius=16, border_width=1)
        self.grid_columnconfigure(0, weight=1)
        if title:
            ctk.CTkLabel(self, text=title.upper(), font=font(11, "bold"), text_color=MUTED).grid(
                row=0, column=0, sticky="w", padx=16, pady=(12, 2))


class Field(ctk.CTkFrame):
    """Label + entry + hint line."""

    def __init__(self, master: Any, label: str, hint: str, value: str = "", secret: bool = False,
                 placeholder: str = "") -> None:
        super().__init__(master, fg_color="transparent")
        self.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self, text=label, font=font(13, "bold"), text_color=TEXT).grid(row=0, column=0, sticky="w")
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.grid(row=1, column=0, sticky="ew", pady=(4, 2))
        row.grid_columnconfigure(0, weight=1)
        # No textvariable: CTkEntry placeholders only work without one.
        self.entry = ctk.CTkEntry(row, height=36, corner_radius=10, font=font(13),
                                  fg_color=CARD_2, border_color=BORDER, text_color=TEXT,
                                  placeholder_text=placeholder or None)
        self.entry.grid(row=0, column=0, sticky="ew")
        self.secret, self.revealed = secret, False
        if secret:
            self.entry.configure(show="•")
            ctk.CTkButton(row, text="👁", width=36, height=36, corner_radius=10, fg_color=CARD_2,
                          hover_color=BORDER, border_width=1, border_color=BORDER,
                          command=self._toggle).grid(row=0, column=1, padx=(6, 0))
        ctk.CTkLabel(self, text=hint, font=font(11), text_color=MUTED, anchor="w", justify="left",
                     wraplength=400).grid(row=2, column=0, sticky="w")
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


class PrinterCard(ctk.CTkFrame):
    """One printer on the dashboard: photo, progress ring, job and a few numbers."""

    def __init__(self, master: Any, images: Images, on_click: Callable[[], None]) -> None:
        super().__init__(master, fg_color=CARD, corner_radius=18, border_width=1, border_color=BORDER)
        self.images = images
        self.grid_columnconfigure(0, weight=1)

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 0))
        head.grid_columnconfigure(1, weight=1)
        self.dot = ctk.CTkLabel(head, text="●", font=font(13), text_color=MUTED)
        self.dot.grid(row=0, column=0, padx=(0, 6))
        self.name = ctk.CTkLabel(head, text="", font=font(14, "bold"), text_color=TEXT, anchor="w")
        self.name.grid(row=0, column=1, sticky="w")
        self.host = ctk.CTkLabel(head, text="", font=font(11), text_color=MUTED)
        self.host.grid(row=0, column=2, sticky="e")

        mid = ctk.CTkFrame(self, fg_color="transparent")
        mid.grid(row=1, column=0, sticky="ew", padx=16, pady=(12, 0))
        mid.grid_columnconfigure(1, weight=1)
        self.photo = ctk.CTkLabel(mid, text="")
        self.photo.grid(row=0, column=0, sticky="w")
        self.ring = ctk.CTkLabel(mid, text="", font=font(19, "bold"), text_color=TEXT, compound="center")
        self.ring.grid(row=0, column=2, sticky="e")

        self.job = ctk.CTkLabel(self, text="", font=font(16, "bold"), text_color=TEXT, anchor="w")
        self.job.grid(row=2, column=0, sticky="w", padx=16, pady=(12, 0))
        self.sub = ctk.CTkLabel(self, text="", font=font(12), text_color=MUTED, anchor="w")
        self.sub.grid(row=3, column=0, sticky="w", padx=16)

        tiles = ctk.CTkFrame(self, fg_color="transparent")
        tiles.grid(row=4, column=0, sticky="ew", padx=12, pady=(10, 14))
        self.values: list[tuple[ctk.CTkLabel, ctk.CTkLabel]] = []
        for i in range(3):
            tiles.grid_columnconfigure(i, weight=1, uniform="t")
            t = ctk.CTkFrame(tiles, fg_color=CARD_2, corner_radius=10)
            t.grid(row=0, column=i, sticky="ew", padx=4)
            label = ctk.CTkLabel(t, text="", font=font(11), text_color=MUTED)
            label.pack(anchor="w", padx=10, pady=(6, 0))
            value = ctk.CTkLabel(t, text="—", font=font(13, "bold"), text_color=TEXT)
            value.pack(anchor="w", padx=10, pady=(0, 6))
            self.values.append((label, value))
        bind_click(self, on_click)

    def show(self, p: dict[str, Any], s: PrinterStatus | None, featured: bool, running: bool) -> None:
        state = s.state if s else State.OFFLINE
        color = STATE_COLORS[state]
        self.configure(border_color=GREEN if featured else BORDER, border_width=2 if featured else 1)
        self.dot.configure(text_color=color)
        self.name.configure(text=printer_name(p))
        self.host.configure(text=p.get("host", ""))
        self.photo.configure(image=self.images.photo(printer_image(p), 92))

        if not running or s is None:
            ring_text, pct = "—", None
        elif state in (State.PRINTING, State.PAUSED):
            ring_text, pct = f"{s.progress or 0}%", s.progress or 0
        elif state == State.FINISHED:
            ring_text, pct = "✓", 100
        else:
            ring_text, pct = tr(f"state.{state.value}"), None
        self.ring.configure(image=self.images.ring(pct, color), text=ring_text,
                            font=font(19 if len(ring_text) <= 4 else 12, "bold"),
                            text_color=TEXT if pct is not None else MUTED)

        if not running:
            job, sub = tr("home.not_started"), tr("card.edit")
        elif s is None or state == State.OFFLINE:
            job, sub = tr("home.unreachable"), ""
        else:
            job = tr("home.calibration") if s.calibration else (s.job_name or tr("home.no_job"))
            sub = filament_label(s.filament, s.filament_color, i18n.current()) or tr(f"state.{state.value}")
        self.job.configure(text=job if len(job) <= 28 else job[:27] + "…")
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

        cache = settings.settings_path().parent / "cache"
        self.art = PrinterArt(resource("assets"), cache, lambda: self.events.put(("art", None)))
        self.art.use_app(client_id_from(self.cfg))
        self.images = Images(self.art)

        logging.getLogger().addHandler(QueueHandler(self.events))
        logging.getLogger().setLevel(logging.INFO)

        root.title("Print Presence")
        root.geometry("1000x680")
        root.minsize(720, 560)
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
            threading.Thread(target=lambda: self.events.put(("update", updates.check())), daemon=True).start()

    def _app_icon(self) -> Image.Image:
        return self.art.local("printer") or Image.new("RGBA", (64, 64), (31, 35, 43, 255))

    def _set_icon(self) -> None:
        ico = resource("assets/app.ico")
        if sys.platform == "win32" and ico.exists():
            # CustomTkinter sets its own icon shortly after start; override it after that.
            self.root.after(250, lambda: self.root.iconbitmap(str(ico)))
        else:
            try:
                self._icon = tk.PhotoImage(file=resource("assets/printer.png")).subsample(8)
                self.root.iconphoto(True, self._icon)
            except tk.TclError:
                pass

    def _running(self) -> bool:
        return self.runner is not None and self.runner.running

    # Layout ----------------------------------------------------------------

    def _build(self) -> None:
        root = self.root
        root.grid_columnconfigure(0, weight=1)
        root.grid_rowconfigure(2, weight=1)
        self.cards = []
        self.columns = 0

        top = ctk.CTkFrame(root, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=22, pady=(18, 12))
        top.grid_columnconfigure(2, weight=1)
        self._logo = ctk.CTkImage(self._app_icon(), size=(38, 38))
        ctk.CTkLabel(top, image=self._logo, text="").grid(row=0, column=0, padx=(0, 10))
        title = ctk.CTkFrame(top, fg_color="transparent")
        title.grid(row=0, column=1, sticky="w")
        ctk.CTkLabel(title, text="Print Presence", font=font(18, "bold"), text_color=TEXT,
                     height=22).pack(anchor="w")
        ctk.CTkLabel(title, text=f"v{__version__}", font=font(11), text_color=MUTED, height=16).pack(anchor="w")

        self.PAGES = {"farm": tr("tab.farm"), "settings": tr("tab.settings"), "log": tr("tab.log")}
        self.nav = ctk.CTkSegmentedButton(top, values=list(self.PAGES.values()), font=font(13, "bold"),
                                          height=34, corner_radius=10, fg_color=CARD,
                                          selected_color="#262c3d", selected_hover_color="#2d3447",
                                          unselected_color=CARD, unselected_hover_color=CARD_2,
                                          text_color=TEXT, command=self.show_page)
        self.nav.grid(row=0, column=2, sticky="w", padx=(24, 0))

        self.pill = ctk.CTkLabel(top, text="", font=font(12, "bold"), corner_radius=14, height=32)
        self.pill.grid(row=0, column=3, padx=(10, 10))
        self.button = ctk.CTkButton(top, text="", width=150, height=38, corner_radius=12, font=font(14, "bold"),
                                    command=self.toggle)
        self.button.grid(row=0, column=4)

        self.update_btn = ctk.CTkButton(root, text="", height=32, corner_radius=10, font=font(13, "bold"),
                                        fg_color="#1d3b2a", hover_color="#24503a", text_color="#7ee2a8",
                                        command=lambda: self.update_info and webbrowser.open(self.update_info[1]))
        if self.update_info:
            self._show_update(self.update_info)

        pages = ctk.CTkFrame(root, fg_color="transparent")
        pages.grid(row=2, column=0, sticky="nsew", padx=22, pady=(0, 18))
        pages.grid_columnconfigure(0, weight=1)
        pages.grid_rowconfigure(0, weight=1)
        self.pages: dict[str, ctk.CTkFrame] = {}
        for key in self.PAGES:
            page = ctk.CTkFrame(pages, fg_color="transparent")
            page.grid(row=0, column=0, sticky="nsew")
            page.grid_columnconfigure(0, weight=1)
            self.pages[key] = page
        self._build_farm(self.pages["farm"])
        self._build_settings(self.pages["settings"])
        self._build_log(self.pages["log"])
        self.show_page("farm")
        self._update_button()

    def show_page(self, label_or_key: str) -> None:
        key = next((k for k, v in self.PAGES.items() if label_or_key in (k, v)), "farm")
        self.pages[key].tkraise()
        self.nav.set(self.PAGES[key])

    def _build_farm(self, page: ctk.CTkFrame) -> None:
        page.grid_rowconfigure(1, weight=1)
        strip = ctk.CTkFrame(page, fg_color=STRIP, corner_radius=16, border_width=1, border_color=STRIP_BORDER)
        strip.grid(row=0, column=0, sticky="ew", pady=(0, 14), padx=6)
        strip.grid_columnconfigure(1, weight=1)
        self.st_image = ctk.CTkLabel(strip, text="")
        self.st_image.grid(row=0, column=0, rowspan=3, padx=(16, 14), pady=12)
        ctk.CTkLabel(strip, text=tr("strip.now"), font=font(11, "bold"), text_color="#9aa3ff",
                     height=16).grid(row=0, column=1, sticky="sw", pady=(14, 0))
        self.st_title = ctk.CTkLabel(strip, text="", font=font(14, "bold"), text_color=TEXT, anchor="w", height=20)
        self.st_title.grid(row=1, column=1, sticky="w")
        self.st_line = ctk.CTkLabel(strip, text="", font=font(13), text_color="#c5cad3", anchor="w", height=18)
        self.st_line.grid(row=2, column=1, sticky="nw", pady=(0, 14))
        self.st_button = ctk.CTkLabel(strip, text="", font=font(12, "bold"), fg_color=BLURPLE, corner_radius=8,
                                      text_color="#ffffff", height=32)

        self.grid = ctk.CTkScrollableFrame(page, fg_color="transparent")
        self.grid.grid(row=1, column=0, sticky="nsew")
        self.grid.bind("<Configure>", lambda _e: self._layout_cards(), add="+")

        self.add_card = ctk.CTkFrame(self.grid, fg_color="transparent", corner_radius=18, border_width=2,
                                     border_color="#2a2f40", height=290)
        self.add_card.grid_propagate(False)
        self.add_card.grid_columnconfigure(0, weight=1)
        self.add_card.grid_rowconfigure((0, 4), weight=1)
        ctk.CTkLabel(self.add_card, text="+", font=font(36), text_color="#6b7386").grid(row=1, column=0)
        ctk.CTkLabel(self.add_card, text=tr("card.add"), font=font(14), text_color="#9aa1b2").grid(row=2, column=0)
        ctk.CTkLabel(self.add_card, text=tr("card.add_hint"), font=font(12), text_color="#6b7386").grid(
            row=3, column=0)
        bind_click(self.add_card, self._add_from_farm)

    def _switch(self, parent: Any, row: int, text: str, value: bool, command=None) -> tk.BooleanVar:
        var = tk.BooleanVar(value=value)
        ctk.CTkSwitch(parent, text=text, variable=var, font=font(13), progress_color=GREEN, command=command).grid(
            row=row, column=0, sticky="w", padx=16, pady=4)
        return var

    def _build_settings(self, page: ctk.CTkFrame) -> None:
        page.grid_rowconfigure(0, weight=1)
        scroll = ctk.CTkScrollableFrame(page, fg_color="transparent")
        scroll.grid(row=0, column=0, sticky="nsew")
        scroll.grid_columnconfigure((0, 1), weight=1, uniform="s")

        # Printers (left column)
        card = Card(scroll, tr("set.printers"))
        card.grid(row=0, column=0, rowspan=2, sticky="new", padx=(0, 8))
        pick = ctk.CTkFrame(card, fg_color="transparent")
        pick.grid(row=1, column=0, sticky="ew", padx=16, pady=(6, 4))
        pick.grid_columnconfigure(0, weight=1)
        self.printer_menu = ctk.CTkOptionMenu(pick, values=[""], height=36, corner_radius=10, font=font(13, "bold"),
                                              fg_color=CARD_2, button_color=BORDER, button_hover_color=BORDER,
                                              dropdown_font=font(13), command=self._on_pick)
        self.printer_menu.grid(row=0, column=0, sticky="ew")
        self.add_btn = ctk.CTkButton(pick, text=tr("set.add_printer"), width=96, height=36, corner_radius=10,
                                     font=font(13), fg_color=CARD_2, hover_color=BORDER, border_width=1,
                                     border_color=BORDER, command=self._add_printer)
        self.add_btn.grid(row=0, column=1, padx=(6, 0))
        self.remove_btn = ctk.CTkButton(pick, text=tr("set.remove_printer"), width=96, height=36, corner_radius=10,
                                        font=font(13), fg_color=CARD_2, hover_color="#3a2326", text_color="#ff8a8e",
                                        border_width=1, border_color=BORDER, command=self._remove_printer)
        self.remove_btn.grid(row=0, column=2, padx=(6, 0))

        find = ctk.CTkFrame(card, fg_color="transparent")
        find.grid(row=2, column=0, sticky="ew", padx=16, pady=(6, 4))
        find.grid_columnconfigure(1, weight=1)
        self.find_btn = ctk.CTkButton(find, text=tr("set.find"), height=36, corner_radius=10,
                                      font=font(13, "bold"), fg_color=CARD_2, hover_color=BORDER,
                                      border_width=1, border_color=BORDER, command=self.search)
        self.find_btn.grid(row=0, column=0, sticky="w")
        self.find_info = ctk.CTkLabel(find, text="", font=font(12), text_color=MUTED, anchor="w", justify="left",
                                      wraplength=240)
        self.find_info.grid(row=0, column=1, sticky="w", padx=(10, 0))

        self.f_host = Field(card, tr("set.host"), tr("set.host_hint"), placeholder="192.168.1.50")
        self.f_serial = Field(card, tr("set.serial"), tr("set.serial_hint"))
        self.f_code = Field(card, "Access Code", tr("set.code_hint"), secret=True,
                            placeholder=tr("set.code_placeholder"))
        self.f_name = Field(card, tr("set.name"), tr("set.name_hint"))
        self.fields = (self.f_host, self.f_serial, self.f_code, self.f_name)
        for i, f in enumerate(self.fields):
            f.grid(row=3 + i, column=0, sticky="ew", padx=16, pady=(6, 4 if i < 3 else 16))
        self._load_fields()

        # Discord (right column)
        dc = Card(scroll, "Discord")
        dc.grid(row=0, column=1, sticky="new", padx=(8, 0), pady=(0, 16))
        d, pr = self.cfg["discord"], self.cfg["presence"]
        custom = str(d.get("client_id", ""))
        self.use_default = self._switch(dc, 1, tr("set.default_app"), bool(d.get("use_default", not custom)),
                                        self._update_client_state)
        self.f_client = Field(dc, tr("set.client_id"), tr("set.client_id_hint"), custom)
        self.f_client.grid(row=2, column=0, sticky="ew", padx=16, pady=(4, 0))
        ctk.CTkButton(dc, text=tr("set.custom_app_help"), height=28, fg_color="transparent",
                      hover_color=CARD_2, text_color=LINK, font=font(12), anchor="w",
                      command=lambda: webbrowser.open(docs_url(custom_app=True))).grid(
            row=3, column=0, sticky="w", padx=10)
        self.hide_job = self._switch(dc, 4, tr("set.hide_job"), bool(pr.get("hide_job", False)),
                                     self._refresh_view)
        self.show_button = self._switch(dc, 5, tr("set.button"), bool(pr.get("button", True)),
                                        self._refresh_view)
        self.show_idle = self._switch(dc, 6, tr("set.show_idle"), bool(pr.get("show_when_idle", True)))
        ctk.CTkFrame(dc, fg_color="transparent", height=8).grid(row=7, column=0)

        # Behaviour (right column)
        oc = Card(scroll, tr("set.behaviour"))
        oc.grid(row=1, column=1, sticky="new", padx=(8, 0))
        app = self.cfg["app"]
        row = 1
        if winstartup.supported():
            self.launch_windows = self._switch(oc, row, tr("set.launch_windows"), winstartup.is_enabled(),
                                               self._on_launch_windows)
            row += 1
        if self.tray.available:
            self.close_to_tray = self._switch(oc, row, tr("set.close_to_tray"), bool(app.get("close_to_tray", True)))
            row += 1
        self.autostart = self._switch(oc, row, tr("set.autostart"), bool(app.get("autostart", False)))
        self.check_updates = self._switch(oc, row + 1, tr("set.check_updates"), bool(app.get("check_updates", True)))
        self.ui_lang = self._lang_selector(oc, row + 2, tr("set.ui_lang"), app.get("language", "auto"),
                                           self._on_ui_lang)
        self.lang = self._lang_selector(oc, row + 3, tr("set.status_lang"), pr.get("language", "auto"),
                                        lambda _: self._refresh_view())
        ctk.CTkButton(oc, text=tr("set.instructions"), height=28, fg_color="transparent",
                      hover_color=CARD_2, text_color=LINK, font=font(12),
                      command=lambda: webbrowser.open(docs_url())).grid(row=row + 4, column=0, sticky="w",
                                                                        padx=10, pady=(10, 12))
        self._update_client_state()

    def _build_log(self, page: ctk.CTkFrame) -> None:
        page.grid_rowconfigure(0, weight=1)
        self.log_box = ctk.CTkTextbox(page, fg_color=CARD, border_width=1, border_color=BORDER, corner_radius=14,
                                      font=ctk.CTkFont(family="Consolas", size=12), text_color="#c9ced6")
        self.log_box.grid(row=0, column=0, sticky="nsew")
        self.log_box.configure(state="disabled")

    def _lang_selector(self, card: Card, row: int, label: str, value: str, command) -> ctk.CTkSegmentedButton:
        frame = ctk.CTkFrame(card, fg_color="transparent")
        frame.grid(row=row, column=0, sticky="w", padx=16, pady=(10, 0))
        ctk.CTkLabel(frame, text=label, font=font(13), text_color=TEXT, anchor="w").pack(anchor="w")
        names = [tr("lang.auto"), *LANGUAGE_NAMES.values()]
        seg = ctk.CTkSegmentedButton(frame, values=names, font=font(12), selected_color=GREEN,
                                     selected_hover_color=GREEN_HOVER, command=command)
        seg.set(LANGUAGE_NAMES.get(value, tr("lang.auto")))
        seg.pack(anchor="w", pady=(4, 0))
        return seg

    @staticmethod
    def _lang_choice(seg: ctk.CTkSegmentedButton) -> str:
        return {name: code for code, name in LANGUAGE_NAMES.items()}.get(seg.get(), "auto")

    def _lang_code(self) -> str:
        # "Auto" status language follows the interface language.
        return status_language(self._lang_choice(self.lang), self._lang_choice(self.ui_lang))

    # Dashboard -------------------------------------------------------------

    def _shown_printers(self) -> list[dict[str, Any]]:
        if self._running():
            return self.run_printers
        return [p for p in self.printers if not is_empty(p)]

    def _layout_cards(self, force: bool = False) -> None:
        width = self.grid.winfo_width()
        cols = 3 if width >= 880 else 2 if width >= 560 else 1
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

    def _show_strip(self) -> None:
        printers = self._shown_printers()
        if self._running() and self.statuses and self.featured < len(printers):
            p, s = printers[self.featured], self.statuses[self.featured]
        else:
            p = printers[0] if printers else self.printers[self.sel]
            s = None
        name = printer_name(p)
        activity = build_activity(s, name, self._lang_code(), hide_job=self.hide_job.get()) if s else None
        self.st_title.configure(text=name)
        if activity is None:
            self.st_image.configure(image=self.images.preview(printer_image(p), None))
            if not self._running():
                text = tr("home.press_start")
            elif s is None or s.state == State.OFFLINE:
                text = tr("home.hidden")
            else:
                text = tr("strip.off")
            self.st_line.configure(text=text)
        else:
            self.st_image.configure(image=self.images.preview(printer_image(p), activity.get("small_image")))
            parts = [activity["details"].strip()]
            if activity.get("state"):
                parts.append(activity["state"].strip())
            if activity.get("end") and s and s.remaining_min:
                parts.append(tr("home.time_left", time=fmt_minutes(s.remaining_min)).replace("⏱", "").strip())
            self.st_line.configure(text=" · ".join(parts))
        if self.show_button.get():
            label = {"ru": "Скачать Print Presence", "uk": "Завантажити Print Presence"}.get(
                self._lang_code(), "Get Print Presence")
            self.st_button.configure(text=f"   {label}   ")
            self.st_button.grid(row=0, column=2, rowspan=3, padx=16)
        else:
            self.st_button.grid_remove()

    def _refresh_view(self) -> None:
        self._sync_cards()
        self._show_strip()

    def open_printer(self, index: int) -> None:
        printers = self._shown_printers()
        if index < len(printers) and not self._running():
            target = printers[index]
            self._store_fields()
            self._select(next((i for i, p in enumerate(self.printers) if p is target), self.sel))
        self.show_page("settings")

    def _add_from_farm(self) -> None:
        self.show_page("settings")
        if is_empty(self.printers[-1]):
            self._select(len(self.printers) - 1)
        else:
            self._add_printer()
        self.search()

    # Printer list (settings) -----------------------------------------------

    def _titles(self) -> list[str]:
        titles = []
        for i, p in enumerate(self.printers):
            name = tr("set.new_printer") if is_empty(p) else printer_name(p)
            host = f" · {p['host']}" if p.get("host") else ""
            titles.append(f"{i + 1}. {name}{host}")
        return titles

    def _refresh_menu(self) -> None:
        titles = self._titles()
        self.printer_menu.configure(values=titles)
        self.printer_menu.set(titles[self.sel])

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
        self._refresh_menu()

    def _select(self, index: int) -> None:
        self.sel = max(0, min(index, len(self.printers) - 1))
        self._load_fields()
        if not self._running():
            self._refresh_view()

    def _on_pick(self, title: str) -> None:
        self._store_fields()
        self._select(self._titles().index(title))

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

    # Helpers ---------------------------------------------------------------

    def _update_client_state(self) -> None:
        self.f_client.enable(not self.use_default.get() and not self._running())

    def _set_inputs_enabled(self, on: bool) -> None:
        for f in self.fields:
            f.enable(on)
        state = "normal" if on else "disabled"
        for w in (self.find_btn, self.printer_menu, self.add_btn, self.remove_btn):
            w.configure(state=state)
        self._update_client_state()

    def _collect(self) -> dict[str, Any]:
        self._store_fields()
        cfg = self.cfg
        cfg["printers"] = [dict(p) for p in self.printers if not is_empty(p)]
        cfg.setdefault("discord", {}).update(use_default=self.use_default.get(), client_id=self.f_client.get())
        cfg["presence"].update(show_when_idle=self.show_idle.get(), language=self._lang_choice(self.lang),
                               hide_job=self.hide_job.get(), button=self.show_button.get())
        cfg["app"].update(autostart=self.autostart.get(), language=self._lang_choice(self.ui_lang),
                          check_updates=self.check_updates.get())
        if hasattr(self, "close_to_tray"):
            cfg["app"]["close_to_tray"] = self.close_to_tray.get()
        return cfg

    def _set_pill(self, text: str, color: str) -> None:
        bg = {GREEN: "#11251a", AMBER: "#2a2112", RED: "#2b1416"}.get(color, CARD)
        self.pill.configure(text=f"   ●  {text}   ", text_color=color, fg_color=bg)

    def _update_button(self) -> None:
        if self._running():
            self.button.configure(text=tr("btn.stop"), fg_color=RED, hover_color=RED_HOVER, state="normal")
        else:
            self.button.configure(text=tr("btn.start"), fg_color=GREEN, hover_color=GREEN_HOVER, state="normal")
            self._set_pill(tr("pill.stopped"), MUTED)

    def _on_launch_windows(self) -> None:
        try:
            winstartup.set_enabled(self.launch_windows.get())
        except OSError as e:
            log.warning("%s", e)
            self.launch_windows.set(winstartup.is_enabled())

    def _show_update(self, info: tuple[str, str]) -> None:
        self.update_info = info
        self.update_btn.configure(text=tr("update.available", version=info[0]))
        self.update_btn.grid(row=1, column=0, sticky="ew", padx=28, pady=(0, 12))

    def _on_ui_lang(self, _value: str) -> None:
        """Rebuild the window (and the tray menu) in the newly chosen language."""
        cfg = self._collect()
        settings.save(cfg)
        i18n.set_language(cfg["app"]["language"])
        for child in self.root.winfo_children():
            child.destroy()
        self.tray.stop()
        self.tray = Tray(self._app_icon(), self.events, self._running)
        self._build()
        self.show_page("settings")
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
        self.find_btn.configure(state="disabled", text=tr("set.searching"))
        self.find_info.configure(text=tr("set.listening"), text_color=MUTED)
        threading.Thread(target=lambda: self.events.put(("found", discover(8.0))), daemon=True).start()

    def _on_found(self, found: list[FoundPrinter]) -> None:
        self.searching = False
        self.find_btn.configure(state="disabled" if self._running() else "normal", text=tr("set.find"))
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
        self.featured = 0
        self.runner = Runner(cfg, on_status=lambda s, f, d: self.events.put(("status", (s, f, d))))
        self.runner.start()
        self._set_inputs_enabled(False)
        self._update_button()
        self._set_pill(tr("pill.connecting"), AMBER)
        self.show_page("farm")
        self._refresh_view()
        log.info(tr("log.started"))

    def stop(self) -> None:
        if self.runner:
            self.runner.stop(timeout=0)
        self.button.configure(text=tr("btn.stopping"), state="disabled")

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
        self._refresh_view()
        status = statuses[featured]
        if status.state == State.OFFLINE:
            self._set_pill(tr("pill.no_printer"), AMBER)
        elif not discord_ok:
            self._set_pill(tr("pill.no_discord"), AMBER)
        else:
            self._set_pill(tr("pill.running"), GREEN)
        self.tray.set_tooltip(f"Print Presence — {self.st_line.cget('text')}")

    def _on_tray(self, action: str) -> None:
        if action == "open":
            self.show_window()
        elif action == "toggle":
            self.toggle()
        elif action == "quit":
            self.quit()

    def _poll(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "log":
                    self._append_log(payload)
                elif kind == "status":
                    self._on_status(*payload)
                elif kind == "found":
                    self._on_found(payload)
                elif kind == "art":
                    self.images.clear()
                    self._refresh_view()
                elif kind == "update" and payload:
                    log.info(tr("log.update", version=payload[0]))
                    self._show_update(payload)
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

    def _append_log(self, line: str) -> None:
        self.log_box.configure(state="normal")
        self.log_box.insert("end", line + "\n")
        if int(self.log_box.index("end-1c").split(".")[0]) > 500:
            self.log_box.delete("1.0", "100.0")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")


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
