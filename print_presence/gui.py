"""Print Presence desktop window (CustomTkinter)."""

from __future__ import annotations

import logging
import os
import queue
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from typing import Any
from urllib.parse import quote

import customtkinter as ctk
from PIL import Image, ImageDraw

from . import __version__, i18n, settings, updates, winstartup
from .filament import filament_label
from .i18n import LANGUAGE_NAMES, tr
from .presence import build_activity
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


def docs_url(custom_app: bool = False) -> str:
    return DOCS.get(i18n.current(), DOCS["en"])[1 if custom_app else 0]

FONT = "Segoe UI"
BG = "#0e1014"
CARD = "#171a20"
CARD_2 = "#1f232b"
BORDER = "#272c36"
TEXT = "#e8eaee"
MUTED = "#8a93a3"
GREEN = "#00ae42"
GREEN_HOVER = "#00953a"
RED = "#e5484d"
RED_HOVER = "#c93b40"
AMBER = "#f5a623"
BLUE = "#2ea0ff"
LINK = "#7aa2ff"
DISCORD = "#232428"

STATE_COLORS = {
    State.OFFLINE: MUTED,
    State.IDLE: MUTED,
    State.PREPARING: BLUE,
    State.PRINTING: GREEN,
    State.PAUSED: AMBER,
    State.FINISHED: BLUE,
    State.FAILED: RED,
}


def resource(name: str) -> Path:
    # Files bundled by PyInstaller live in sys._MEIPASS.
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / name


def font(size: int = 13, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(family=FONT, size=size, weight=weight)


def fmt_minutes(minutes: int | None) -> str:
    if not minutes:
        return "—"
    h, m = divmod(int(minutes), 60)
    return tr("time.hm", h=h, m=m) if h else tr("time.m", m=m)


class QueueHandler(logging.Handler):
    def __init__(self, q: queue.Queue) -> None:
        super().__init__()
        self.q = q
        self.setFormatter(logging.Formatter("%(asctime)s  %(message)s", "%H:%M:%S"))

    def emit(self, record: logging.LogRecord) -> None:
        self.q.put(("log", self.format(record)))


class PreviewArt:
    """Builds the Discord-style large image with the small status badge."""

    def __init__(self) -> None:
        self.cache: dict[tuple[str, str], ctk.CTkImage] = {}
        self.large = self._load("printer")

    @staticmethod
    def _load(name: str) -> Image.Image:
        try:
            return Image.open(resource(f"assets/{name}.png")).convert("RGBA")
        except OSError:
            return Image.new("RGBA", (512, 512), CARD_2)

    def get(self, badge: str | None, model_image: str = "printer") -> ctk.CTkImage:
        key = (model_image, badge or "")
        if key not in self.cache:
            large = self._load(model_image)
            size, pad = 240, 30
            img = Image.new("RGBA", (size + pad, size + pad), (0, 0, 0, 0))
            img.paste(large.resize((size, size), Image.LANCZOS), (0, 0))
            if badge:
                try:
                    small = Image.open(resource(f"assets/{badge}.png")).convert("RGBA").resize(
                        (96, 96), Image.LANCZOS)
                    ring = Image.new("RGBA", (116, 116), (0, 0, 0, 0))
                    ImageDraw.Draw(ring).ellipse((0, 0, 115, 115), fill=DISCORD)
                    ring.paste(small, (10, 10), small)
                    img.paste(ring, (size + pad - 116, size + pad - 116), ring)
                except OSError:
                    pass
            self.cache[key] = ctk.CTkImage(img, size=(90, 90))
        return self.cache[key]


class Card(ctk.CTkFrame):
    def __init__(self, master: Any, title: str | None = None, **kw: Any) -> None:
        super().__init__(master, fg_color=CARD, corner_radius=14, border_width=1, border_color=BORDER, **kw)
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
        self.secret = secret
        if secret:
            self.entry.configure(show="•")
            ctk.CTkButton(row, text="👁", width=36, height=36, corner_radius=10, fg_color=CARD_2,
                          hover_color=BORDER, border_width=1, border_color=BORDER,
                          command=self._toggle).grid(row=0, column=1, padx=(6, 0))
        ctk.CTkLabel(self, text=hint, font=font(11), text_color=MUTED, anchor="w", justify="left").grid(
            row=2, column=0, sticky="w")
        if value:
            self.set(value)

    def _toggle(self) -> None:
        self.entry.configure(show="" if self.entry.cget("show") else "•")

    def get(self) -> str:
        return self.entry.get().strip()

    def set(self, value: str) -> None:
        state = self.entry.cget("state")
        self.entry.configure(state="normal")
        self.entry.delete(0, "end")
        if value:
            self.entry.insert(0, value)
        else:
            # CTkEntry only shows its placeholder again after losing focus; show it right away.
            activate = getattr(self.entry, "_activate_placeholder", None)
            if activate:
                activate()
        self.entry.configure(state=state)

    def enable(self, on: bool) -> None:
        self.entry.configure(state="normal" if on else "disabled", text_color=TEXT if on else MUTED)




def printer_name(p: dict[str, Any]) -> str:
    return str(p.get("name") or "").strip() or display_name(p.get("model_code"), p.get("serial"))


def printer_image(p: dict[str, Any]) -> str:
    return image_key(p.get("model_code"), p.get("serial"))


def is_empty(p: dict[str, Any]) -> bool:
    return not any(str(p.get(k) or "").strip() for k in ("host", "serial", "access_code", "name"))


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
        self.update_info: tuple[str, str] | None = None
        self.events: queue.Queue = queue.Queue()
        self.art = PreviewArt()
        self.searching = False

        logging.getLogger().addHandler(QueueHandler(self.events))
        logging.getLogger().setLevel(logging.INFO)

        root.title("Print Presence")
        root.geometry("580x800")
        root.minsize(540, 660)
        root.configure(fg_color=BG)
        self._set_icon()

        self.tray = Tray(self.art.large, self.events, self._running)
        self._build()
        self._show_idle_view()
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

        header = ctk.CTkFrame(root, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 6))
        header.grid_columnconfigure(1, weight=1)
        self._logo = ctk.CTkImage(self.art.large, size=(42, 42))
        ctk.CTkLabel(header, image=self._logo, text="").grid(row=0, column=0, rowspan=2, padx=(0, 12))
        ctk.CTkLabel(header, text="Print Presence", font=font(20, "bold"), text_color=TEXT).grid(
            row=0, column=1, sticky="sw")
        ctk.CTkLabel(header, text=tr("app.subtitle", version=__version__), font=font(12),
                     text_color=MUTED).grid(row=1, column=1, sticky="nw")
        self.pill = ctk.CTkLabel(header, text="", font=font(12, "bold"), fg_color=CARD, corner_radius=12,
                                 height=28)
        self.pill.grid(row=0, column=2, rowspan=2, sticky="e")
        self._set_pill(tr("pill.stopped"), MUTED)

        self.update_btn = ctk.CTkButton(root, text="", height=32, corner_radius=10, font=font(13, "bold"),
                                        fg_color="#1d3b2a", hover_color="#24503a", text_color="#7ee2a8",
                                        command=lambda: self.update_info and webbrowser.open(self.update_info[1]))
        if self.update_info:
            self._show_update(self.update_info)

        tabs = ctk.CTkTabview(root, fg_color="transparent", segmented_button_fg_color=CARD,
                              segmented_button_selected_color=CARD_2,
                              segmented_button_selected_hover_color=BORDER,
                              segmented_button_unselected_color=CARD,
                              segmented_button_unselected_hover_color=CARD_2,
                              text_color=TEXT, anchor="w")
        tabs.grid(row=2, column=0, sticky="nsew", padx=12, pady=(0, 6))
        self.tabs = tabs
        self.TAB_HOME, self.TAB_SETTINGS, self.TAB_LOG = tr("tab.home"), tr("tab.settings"), tr("tab.log")
        for name in (self.TAB_HOME, self.TAB_SETTINGS, self.TAB_LOG):
            tabs.add(name)
            tabs.tab(name).grid_columnconfigure(0, weight=1)

        self._build_home(tabs.tab(self.TAB_HOME))
        self._build_settings(tabs.tab(self.TAB_SETTINGS))
        self._build_log(tabs.tab(self.TAB_LOG))

        self.button = ctk.CTkButton(root, text=tr("btn.start"), height=48, corner_radius=12, font=font(15, "bold"),
                                    fg_color=GREEN, hover_color=GREEN_HOVER, command=self.toggle)
        self.button.grid(row=3, column=0, sticky="ew", padx=20, pady=(4, 18))

    def _build_home(self, tab: ctk.CTkFrame) -> None:
        tab.grid_rowconfigure(0, weight=1)
        scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        scroll.grid(row=0, column=0, sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)

        card = Card(scroll, tr("home.preview"))
        card.grid(row=0, column=0, sticky="ew", pady=(4, 10))
        inner = ctk.CTkFrame(card, fg_color=DISCORD, corner_radius=10)
        inner.grid(row=1, column=0, sticky="ew", padx=12, pady=(4, 12))
        inner.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(inner, text=tr("home.playing"), font=font(11, "bold"), text_color="#b5bac1").grid(
            row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(10, 4))
        self.pv_image = ctk.CTkLabel(inner, text="")
        self.pv_image.grid(row=1, column=0, rowspan=4, padx=(14, 12), pady=(0, 14), sticky="n")
        self.pv_title = ctk.CTkLabel(inner, text="", font=font(14, "bold"), text_color="#f2f3f5", anchor="w")
        self.pv_title.grid(row=1, column=1, sticky="w")
        self.pv_details = ctk.CTkLabel(inner, text="", font=font(13), text_color="#dbdee1", anchor="w")
        self.pv_details.grid(row=2, column=1, sticky="w")
        self.pv_state = ctk.CTkLabel(inner, text="", font=font(13), text_color="#dbdee1", anchor="w")
        self.pv_state.grid(row=3, column=1, sticky="w")
        self.pv_time = ctk.CTkLabel(inner, text="", font=font(12), text_color="#23a55a", anchor="w")
        self.pv_time.grid(row=4, column=1, sticky="nw", pady=(0, 14))

        stats = Card(scroll, tr("home.printer"))
        stats.grid(row=1, column=0, sticky="ew")
        top = ctk.CTkFrame(stats, fg_color="transparent")
        top.grid(row=1, column=0, sticky="ew", padx=16, pady=(2, 0))
        top.grid_columnconfigure(0, weight=1)
        self.st_job = ctk.CTkLabel(top, text="", font=font(15, "bold"), text_color=TEXT, anchor="w")
        self.st_job.grid(row=0, column=0, sticky="w")
        self.st_percent = ctk.CTkLabel(top, text="", font=font(22, "bold"), text_color=GREEN)
        self.st_percent.grid(row=0, column=1, rowspan=2, sticky="e")
        self.st_filament = ctk.CTkLabel(top, text="", font=font(12), text_color=MUTED, anchor="w")
        self.st_filament.grid(row=1, column=0, sticky="w")
        self.st_bar = ctk.CTkProgressBar(stats, height=10, corner_radius=5, fg_color=CARD_2, progress_color=GREEN)
        self.st_bar.grid(row=2, column=0, sticky="ew", padx=16, pady=(8, 12))

        tiles = ctk.CTkFrame(stats, fg_color="transparent")
        tiles.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 14))
        self.tiles: dict[str, ctk.CTkLabel] = {}
        for i, (key, label) in enumerate((("layer", tr("tile.layer")), ("left", tr("tile.left")),
                                          ("nozzle", tr("tile.nozzle")), ("bed", tr("tile.bed")))):
            tiles.grid_columnconfigure(i, weight=1, uniform="t")
            t = ctk.CTkFrame(tiles, fg_color=CARD_2, corner_radius=10)
            t.grid(row=0, column=i, sticky="ew", padx=4)
            ctk.CTkLabel(t, text=label, font=font(11), text_color=MUTED).pack(anchor="w", padx=10, pady=(8, 0))
            v = ctk.CTkLabel(t, text="—", font=font(15, "bold"), text_color=TEXT)
            v.pack(anchor="w", padx=10, pady=(0, 8))
            self.tiles[key] = v

        # Shown only with more than one printer.
        self.all_card = Card(scroll, tr("home.others"))
        self.all_rows = ctk.CTkFrame(self.all_card, fg_color="transparent")
        self.all_rows.grid(row=1, column=0, sticky="ew", padx=16, pady=(2, 12))
        self.all_rows.grid_columnconfigure(1, weight=1)

    def _switch(self, parent: Any, row: int, text: str, value: bool, command=None) -> tk.BooleanVar:
        var = tk.BooleanVar(value=value)
        ctk.CTkSwitch(parent, text=text, variable=var, font=font(13), progress_color=GREEN, command=command).grid(
            row=row, column=0, sticky="w", padx=16, pady=4)
        return var

    def _build_settings(self, tab: ctk.CTkFrame) -> None:
        tab.grid_rowconfigure(0, weight=1)
        scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        scroll.grid(row=0, column=0, sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)

        # Printers
        card = Card(scroll, tr("set.printers"))
        card.grid(row=0, column=0, sticky="ew", pady=(4, 10))
        pick = ctk.CTkFrame(card, fg_color="transparent")
        pick.grid(row=1, column=0, sticky="ew", padx=16, pady=(6, 4))
        pick.grid_columnconfigure(0, weight=1)
        self.printer_menu = ctk.CTkOptionMenu(pick, values=[""], height=36, corner_radius=10, font=font(13, "bold"),
                                              fg_color=CARD_2, button_color=BORDER, button_hover_color=BORDER,
                                              dropdown_font=font(13), command=self._on_pick)
        self.printer_menu.grid(row=0, column=0, sticky="ew")
        self.add_btn = ctk.CTkButton(pick, text=tr("set.add_printer"), width=90, height=36, corner_radius=10,
                                     font=font(13), fg_color=CARD_2, hover_color=BORDER, border_width=1,
                                     border_color=BORDER, command=self._add_printer)
        self.add_btn.grid(row=0, column=1, padx=(6, 0))
        self.remove_btn = ctk.CTkButton(pick, text=tr("set.remove_printer"), width=90, height=36, corner_radius=10,
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
        self.find_info = ctk.CTkLabel(find, text="", font=font(12), text_color=MUTED, anchor="w", justify="left")
        self.find_info.grid(row=0, column=1, sticky="w", padx=(10, 0))

        self.f_host = Field(card, tr("set.host"), tr("set.host_hint"), placeholder="192.168.1.50")
        self.f_serial = Field(card, tr("set.serial"), tr("set.serial_hint"))
        self.f_code = Field(card, "Access Code", tr("set.code_hint"), secret=True,
                            placeholder=tr("set.code_placeholder"))
        self.f_name = Field(card, tr("set.name"), tr("set.name_hint"))
        self.fields = (self.f_host, self.f_serial, self.f_code, self.f_name)
        for i, f in enumerate(self.fields):
            f.grid(row=3 + i, column=0, sticky="ew", padx=16, pady=(6, 4 if i < 3 else 14))
        self._load_fields()

        # Discord
        dc = Card(scroll, "Discord")
        dc.grid(row=1, column=0, sticky="ew", pady=(0, 10))
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
        self.hide_job = self._switch(dc, 4, tr("set.hide_job"), bool(pr.get("hide_job", False)))
        self.show_button = self._switch(dc, 5, tr("set.button"), bool(pr.get("button", True)))
        self.show_idle = self._switch(dc, 6, tr("set.show_idle"), bool(pr.get("show_when_idle", True)))
        ctk.CTkFrame(dc, fg_color="transparent", height=8).grid(row=7, column=0)

        # Behaviour
        oc = Card(scroll, tr("set.behaviour"))
        oc.grid(row=2, column=0, sticky="ew", pady=(0, 10))
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
                                        lambda _: self._show_idle_view() if not self._running() else None)
        ctk.CTkFrame(oc, fg_color="transparent", height=10).grid(row=row + 4, column=0)

        ctk.CTkButton(scroll, text=tr("set.instructions"), height=28, fg_color="transparent",
                      hover_color=CARD, text_color=LINK, font=font(12),
                      command=lambda: webbrowser.open(docs_url())).grid(row=3, column=0, sticky="w")
        self._update_client_state()

    def _build_log(self, tab: ctk.CTkFrame) -> None:
        tab.grid_rowconfigure(0, weight=1)
        self.log_box = ctk.CTkTextbox(tab, fg_color=CARD, border_width=1, border_color=BORDER, corner_radius=12,
                                      font=ctk.CTkFont(family="Consolas", size=12), text_color="#c9ced6")
        self.log_box.grid(row=0, column=0, sticky="nsew", pady=4)
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

    # Printer list ----------------------------------------------------------

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
            self._show_idle_view()

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
        self.pill.configure(text=f"   ●  {text}   ", text_color=color)

    def _on_launch_windows(self) -> None:
        try:
            winstartup.set_enabled(self.launch_windows.get())
        except OSError as e:
            log.warning("%s", e)
            self.launch_windows.set(winstartup.is_enabled())

    def _show_update(self, info: tuple[str, str]) -> None:
        self.update_info = info
        self.update_btn.configure(text=tr("update.available", version=info[0]))
        self.update_btn.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 8))

    def _on_ui_lang(self, _value: str) -> None:
        """Rebuild the window (and the tray menu) in the newly chosen language."""
        cfg = self._collect()
        settings.save(cfg)
        i18n.set_language(cfg["app"]["language"])
        for child in self.root.winfo_children():
            child.destroy()
        self.tray.stop()
        self.tray = Tray(self.art.large, self.events, self._running)
        self._build()
        self.tabs.set(self.TAB_SETTINGS)
        if self._running():
            self._set_inputs_enabled(False)
            self.button.configure(text=tr("btn.stop"), fg_color=RED, hover_color=RED_HOVER)
            if self.statuses:
                self._on_status(self.statuses, self.featured, True)
            else:
                self._set_pill(tr("pill.connecting"), AMBER)
        else:
            self._show_idle_view()

    # Discovery -------------------------------------------------------------

    def search(self) -> None:
        if self.searching:
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
            self.tabs.set(self.TAB_SETTINGS)
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
            self.tabs.set(self.TAB_SETTINGS)
            self._set_pill(tr("pill.fill_settings"), AMBER)
            self.find_info.configure(text=str(e), text_color=AMBER)
            log.warning("%s", e)
            if self.root.state() == "withdrawn":
                self.show_window()
            return
        self.run_printers = [dict(p) for p in cfg["printers"]]
        self.statuses = []
        self.runner = Runner(cfg, on_status=lambda s, f, d: self.events.put(("status", (s, f, d))))
        self.runner.start()
        self._set_inputs_enabled(False)
        self.button.configure(text=tr("btn.stop"), fg_color=RED, hover_color=RED_HOVER)
        self._set_pill(tr("pill.connecting"), AMBER)
        self.tabs.set(self.TAB_HOME)
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

    # Live view -------------------------------------------------------------

    def _show_idle_view(self) -> None:
        p = self.printers[self.sel]
        self._show_preview(None, p)
        self._show_stats(PrinterStatus())
        self._show_all([])

    def _show_preview(self, status: PrinterStatus | None, p: dict[str, Any]) -> None:
        name = printer_name(p)
        activity = build_activity(status, name, self._lang_code(), hide_job=self.hide_job.get()) if status else None
        self.pv_title.configure(text=name)
        if activity is None:
            self.pv_image.configure(image=self.art.get(None, printer_image(p)))
            self.pv_details.configure(text=tr("home.press_start") if status is None else tr("home.hidden"))
            self.pv_state.configure(text="")
            self.pv_time.configure(text="")
            return
        self.pv_image.configure(image=self.art.get(activity.get("small_image"), printer_image(p)))
        self.pv_details.configure(text=activity["details"].strip())
        self.pv_state.configure(text=activity.get("state", "").strip())
        left = status.remaining_min if activity.get("end") else None
        self.pv_time.configure(text=tr("home.time_left", time=fmt_minutes(left)) if left else "")

    def _show_stats(self, s: PrinterStatus) -> None:
        color = STATE_COLORS[s.state]
        if s.state == State.OFFLINE:
            self.st_job.configure(text=tr("home.unreachable") if self.runner else tr("home.not_started"))
        else:
            self.st_job.configure(text=tr("home.calibration") if s.calibration else (s.job_name or tr("home.no_job")))
        fil = filament_label(s.filament, s.filament_color, i18n.current())
        self.st_filament.configure(text=tr("home.filament", name=fil) if fil else "")
        pct = s.progress if s.state != State.OFFLINE else None
        self.st_percent.configure(text=f"{pct}%" if pct is not None else "", text_color=color)
        self.st_bar.configure(progress_color=color)
        self.st_bar.set((pct or 0) / 100)
        self.tiles["layer"].configure(text=f"{s.layer}/{s.total_layers}" if s.total_layers else "—")
        self.tiles["left"].configure(text=fmt_minutes(s.remaining_min) if s.state == State.PRINTING else "—")
        self.tiles["nozzle"].configure(text=f"{s.nozzle_temp:.0f}°" if s.nozzle_temp is not None else "—")
        self.tiles["bed"].configure(text=f"{s.bed_temp:.0f}°" if s.bed_temp is not None else "—")

    def _show_all(self, statuses: list[PrinterStatus]) -> None:
        for child in self.all_rows.winfo_children():
            child.destroy()
        if len(statuses) < 2:
            self.all_card.grid_forget()
            return
        self.all_card.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        for i, (s, p) in enumerate(zip(statuses, self.run_printers)):
            color = STATE_COLORS[s.state]
            ctk.CTkLabel(self.all_rows, text="●", font=font(14), text_color=color).grid(row=i, column=0, padx=(0, 8))
            weight = "bold" if i == self.featured else "normal"
            ctk.CTkLabel(self.all_rows, text=printer_name(p), font=font(13, weight), text_color=TEXT,
                         anchor="w").grid(row=i, column=1, sticky="w")
            info = tr(f"state.{s.state.value}")
            if s.state in (State.PRINTING, State.PAUSED) and s.progress is not None:
                info += f" · {s.progress}%"
            ctk.CTkLabel(self.all_rows, text=info, font=font(12), text_color=MUTED).grid(row=i, column=2, sticky="e")

    def _on_status(self, statuses: list[PrinterStatus], featured: int, discord_ok: bool) -> None:
        if not self._running() or not statuses:
            return
        self.statuses, self.featured = statuses, featured
        status, p = statuses[featured], self.run_printers[featured]
        self._show_preview(status, p)
        self._show_stats(status)
        self._show_all(statuses)
        if status.state == State.OFFLINE:
            self._set_pill(tr("pill.no_printer"), AMBER)
        elif not discord_ok:
            self._set_pill(tr("pill.no_discord"), AMBER)
        else:
            self._set_pill(tr("pill.running"), GREEN)
        text = self.pv_details.cget("text")
        state = self.pv_state.cget("text")
        self.tray.set_tooltip(f"Print Presence — {text}" + (f" · {state}" if state else ""))

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
            self.button.configure(text=tr("btn.start"), state="normal", fg_color=GREEN, hover_color=GREEN_HOVER)
            self._set_inputs_enabled(True)
            self._set_pill(tr("pill.stopped"), MUTED)
            self._show_idle_view()
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
