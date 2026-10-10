"""Print Presence desktop window (CustomTkinter)."""

from __future__ import annotations

import logging
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

from . import __version__, settings
from .presence import build_activity
from .printers.bambu_discovery import FoundPrinter, discover, display_name
from .runner import Runner, validate
from .status import PrinterStatus, State

log = logging.getLogger("print_presence")

REPO_URL = "https://github.com/B0D1KG0/print-presence"
CUSTOM_APP_HELP = REPO_URL + "#" + quote("своё-discord-приложение-необязательно")

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
    return f"{h} ч {m:02d} мин" if h else f"{m} мин"


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
        self.cache: dict[str, ctk.CTkImage] = {}
        try:
            self.large = Image.open(resource("assets/printer.png")).convert("RGBA")
        except OSError:
            self.large = Image.new("RGBA", (512, 512), CARD_2)

    def get(self, badge: str | None) -> ctk.CTkImage:
        key = badge or ""
        if key not in self.cache:
            size, pad = 240, 30
            img = Image.new("RGBA", (size + pad, size + pad), (0, 0, 0, 0))
            img.paste(self.large.resize((size, size), Image.LANCZOS), (0, 0))
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
            self.root_focus()
        self.entry.configure(state=state)

    def root_focus(self) -> None:
        # Moving focus away makes CTkEntry show its placeholder again.
        self.winfo_toplevel().focus_set()

    def enable(self, on: bool) -> None:
        self.entry.configure(state="normal" if on else "disabled", text_color=TEXT if on else MUTED)


class App:
    def __init__(self, root: ctk.CTk) -> None:
        self.root = root
        self.cfg = settings.load()
        self.runner: Runner | None = None
        self.events: queue.Queue = queue.Queue()
        self.art = PreviewArt()
        self.found: list[FoundPrinter] = []
        self.searching = False

        logging.getLogger().addHandler(QueueHandler(self.events))
        logging.getLogger().setLevel(logging.INFO)

        root.title("Print Presence")
        root.geometry("560x780")
        root.minsize(520, 660)
        root.configure(fg_color=BG)
        self._set_icon()

        self._build()
        self._show_preview(None)
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.after(200, self._poll)

        if not self.f_host.get():
            root.after(400, self.search)  # first launch: look for the printer right away
        elif self.cfg["app"].get("autostart"):
            root.after(500, self.start)

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

    # Layout ----------------------------------------------------------------

    def _build(self) -> None:
        root = self.root
        root.grid_columnconfigure(0, weight=1)
        root.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(root, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 6))
        header.grid_columnconfigure(1, weight=1)
        self._logo = ctk.CTkImage(self.art.large, size=(42, 42))
        ctk.CTkLabel(header, image=self._logo, text="").grid(row=0, column=0, rowspan=2, padx=(0, 12))
        ctk.CTkLabel(header, text="Print Presence", font=font(20, "bold"), text_color=TEXT).grid(
            row=0, column=1, sticky="sw")
        ctk.CTkLabel(header, text=f"Статус 3D-принтера в Discord · v{__version__}", font=font(12),
                     text_color=MUTED).grid(row=1, column=1, sticky="nw")
        self.pill = ctk.CTkLabel(header, text="", font=font(12, "bold"), fg_color=CARD, corner_radius=12,
                                 height=28)
        self.pill.grid(row=0, column=2, rowspan=2, sticky="e")
        self._set_pill("Остановлено", MUTED)

        tabs = ctk.CTkTabview(root, fg_color="transparent", segmented_button_fg_color=CARD,
                              segmented_button_selected_color=CARD_2,
                              segmented_button_selected_hover_color=BORDER,
                              segmented_button_unselected_color=CARD,
                              segmented_button_unselected_hover_color=CARD_2,
                              text_color=TEXT, anchor="w")
        tabs.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 6))
        self.tabs = tabs
        for name in ("Главная", "Настройки", "Журнал"):
            tabs.add(name)
            tabs.tab(name).grid_columnconfigure(0, weight=1)

        self._build_home(tabs.tab("Главная"))
        self._build_settings(tabs.tab("Настройки"))
        self._build_log(tabs.tab("Журнал"))

        self.button = ctk.CTkButton(root, text="▶   Запустить", height=48, corner_radius=12, font=font(15, "bold"),
                                    fg_color=GREEN, hover_color=GREEN_HOVER, command=self.toggle)
        self.button.grid(row=2, column=0, sticky="ew", padx=20, pady=(4, 18))

    def _build_home(self, tab: ctk.CTkFrame) -> None:
        card = Card(tab, "Так тебя видят в Discord")
        card.grid(row=0, column=0, sticky="ew", pady=(4, 10))
        inner = ctk.CTkFrame(card, fg_color=DISCORD, corner_radius=10)
        inner.grid(row=1, column=0, sticky="ew", padx=12, pady=(4, 12))
        inner.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(inner, text="ИГРАЕТ В", font=font(11, "bold"), text_color="#b5bac1").grid(
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

        stats = Card(tab, "Принтер")
        stats.grid(row=1, column=0, sticky="ew")
        top = ctk.CTkFrame(stats, fg_color="transparent")
        top.grid(row=1, column=0, sticky="ew", padx=16, pady=(2, 0))
        top.grid_columnconfigure(0, weight=1)
        self.st_job = ctk.CTkLabel(top, text="", font=font(15, "bold"), text_color=TEXT, anchor="w")
        self.st_job.grid(row=0, column=0, sticky="w")
        self.st_percent = ctk.CTkLabel(top, text="", font=font(22, "bold"), text_color=GREEN)
        self.st_percent.grid(row=0, column=1, sticky="e")
        self.st_bar = ctk.CTkProgressBar(stats, height=10, corner_radius=5, fg_color=CARD_2, progress_color=GREEN)
        self.st_bar.grid(row=2, column=0, sticky="ew", padx=16, pady=(8, 12))

        tiles = ctk.CTkFrame(stats, fg_color="transparent")
        tiles.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 14))
        self.tiles: dict[str, ctk.CTkLabel] = {}
        for i, (key, label) in enumerate((("layer", "Слой"), ("left", "Осталось"),
                                          ("nozzle", "Сопло"), ("bed", "Стол"))):
            tiles.grid_columnconfigure(i, weight=1, uniform="t")
            t = ctk.CTkFrame(tiles, fg_color=CARD_2, corner_radius=10)
            t.grid(row=0, column=i, sticky="ew", padx=4)
            ctk.CTkLabel(t, text=label, font=font(11), text_color=MUTED).pack(anchor="w", padx=10, pady=(8, 0))
            v = ctk.CTkLabel(t, text="—", font=font(15, "bold"), text_color=TEXT)
            v.pack(anchor="w", padx=10, pady=(0, 8))
            self.tiles[key] = v
        self._show_stats(PrinterStatus())

    def _build_settings(self, tab: ctk.CTkFrame) -> None:
        tab.grid_rowconfigure(0, weight=1)
        scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        scroll.grid(row=0, column=0, sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)
        p = self.cfg["printer"]

        card = Card(scroll, "Принтер")
        card.grid(row=0, column=0, sticky="ew", pady=(4, 10))
        find = ctk.CTkFrame(card, fg_color="transparent")
        find.grid(row=1, column=0, sticky="ew", padx=16, pady=(6, 4))
        find.grid_columnconfigure(1, weight=1)
        self.find_btn = ctk.CTkButton(find, text="🔍  Найти принтер в сети", height=36, corner_radius=10,
                                      font=font(13, "bold"), fg_color=CARD_2, hover_color=BORDER,
                                      border_width=1, border_color=BORDER, command=self.search)
        self.find_btn.grid(row=0, column=0, sticky="w")
        self.find_info = ctk.CTkLabel(find, text="", font=font(12), text_color=MUTED, anchor="w", justify="left")
        self.find_info.grid(row=0, column=1, sticky="w", padx=(10, 0))
        self.found_menu = ctk.CTkOptionMenu(card, values=[""], height=34, corner_radius=10, font=font(12),
                                            fg_color=CARD_2, button_color=BORDER, button_hover_color=BORDER,
                                            command=self._choose_found)

        self.f_host = Field(card, "IP принтера", "Находится автоматически, или: экран принтера → Настройки → WLAN",
                            p.get("host", ""), placeholder="192.168.1.50")
        self.f_serial = Field(card, "Серийный номер", "Находится автоматически, или: Bambu Studio → Устройство",
                              p.get("serial", ""))
        self.f_code = Field(card, "Access Code",
                            "Принтер его не сообщает — смотри на экране: Настройки → WLAN → Access Code",
                            p.get("access_code", ""), secret=True, placeholder="8 символов")
        self.f_name = Field(card, "Имя в Discord", "Оставь пустым — подставится модель принтера",
                            p.get("name", ""), placeholder=self._auto_name(p.get("serial", "")))
        for i, f in enumerate((self.f_host, self.f_serial, self.f_code, self.f_name)):
            f.grid(row=3 + i, column=0, sticky="ew", padx=16, pady=(6, 4 if i < 3 else 14))

        dc = Card(scroll, "Discord")
        dc.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        d = self.cfg["discord"]
        custom = str(d.get("client_id", ""))
        self.use_default = tk.BooleanVar(value=bool(d.get("use_default", not custom)))
        ctk.CTkSwitch(dc, text="Стандартное оформление (иконки уже готовы)", variable=self.use_default,
                      font=font(13), progress_color=GREEN, command=self._update_client_state).grid(
            row=1, column=0, sticky="w", padx=16, pady=(6, 8))
        self.f_client = Field(dc, "Своё Application ID",
                              "Только если хочешь свои иконки и название — выключи переключатель выше", custom)
        self.f_client.grid(row=2, column=0, sticky="ew", padx=16)
        ctk.CTkButton(dc, text="Как создать своё приложение →", height=28, fg_color="transparent",
                      hover_color=CARD_2, text_color=LINK, font=font(12), anchor="w",
                      command=lambda: webbrowser.open(CUSTOM_APP_HELP)).grid(
            row=3, column=0, sticky="w", padx=10, pady=(0, 12))

        oc = Card(scroll, "Поведение")
        oc.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        self.show_idle = tk.BooleanVar(value=bool(self.cfg["presence"].get("show_when_idle", True)))
        self.autostart = tk.BooleanVar(value=bool(self.cfg["app"].get("autostart", False)))
        ctk.CTkSwitch(oc, text="Показывать статус, когда принтер простаивает", variable=self.show_idle,
                      font=font(13), progress_color=GREEN).grid(row=1, column=0, sticky="w", padx=16, pady=(6, 4))
        ctk.CTkSwitch(oc, text="Включать сразу при открытии программы", variable=self.autostart,
                      font=font(13), progress_color=GREEN).grid(row=2, column=0, sticky="w", padx=16, pady=4)
        lang = ctk.CTkFrame(oc, fg_color="transparent")
        lang.grid(row=3, column=0, sticky="w", padx=16, pady=(8, 14))
        ctk.CTkLabel(lang, text="Язык статуса", font=font(13), text_color=TEXT).pack(side="left", padx=(0, 10))
        self.lang = ctk.CTkSegmentedButton(lang, values=["Русский", "English"], font=font(12),
                                           selected_color=GREEN, selected_hover_color=GREEN_HOVER)
        self.lang.set("English" if self.cfg["presence"].get("language") == "en" else "Русский")
        self.lang.pack(side="left")

        ctk.CTkButton(scroll, text="Инструкция на GitHub →", height=28, fg_color="transparent",
                      hover_color=CARD, text_color=LINK, font=font(12),
                      command=lambda: webbrowser.open(REPO_URL + "#readme")).grid(row=3, column=0, sticky="w")
        self._update_client_state()

    def _build_log(self, tab: ctk.CTkFrame) -> None:
        tab.grid_rowconfigure(0, weight=1)
        self.log_box = ctk.CTkTextbox(tab, fg_color=CARD, border_width=1, border_color=BORDER, corner_radius=12,
                                      font=ctk.CTkFont(family="Consolas", size=12), text_color="#c9ced6")
        self.log_box.grid(row=0, column=0, sticky="nsew", pady=4)
        self.log_box.configure(state="disabled")

    # Helpers ---------------------------------------------------------------

    def _auto_name(self, serial: str | None = None) -> str:
        if serial is None:
            serial = self.f_serial.get()
        return display_name(self.cfg["printer"].get("model_code"), serial)

    def _lang_code(self) -> str:
        return "en" if self.lang.get() == "English" else "ru"

    def _printer_name(self) -> str:
        return self.f_name.get() or self._auto_name()

    def _update_client_state(self) -> None:
        running = self.runner is not None and self.runner.running
        self.f_client.enable(not self.use_default.get() and not running)

    def _set_inputs_enabled(self, on: bool) -> None:
        for f in (self.f_host, self.f_serial, self.f_code, self.f_name):
            f.enable(on)
        self.find_btn.configure(state="normal" if on else "disabled")
        self._update_client_state()

    def _collect(self) -> dict[str, Any]:
        cfg = self.cfg
        cfg.setdefault("printer", {}).update(
            host=self.f_host.get(), serial=self.f_serial.get(), access_code=self.f_code.get(),
            name=self.f_name.get())
        cfg.setdefault("discord", {}).update(use_default=self.use_default.get(), client_id=self.f_client.get())
        cfg["presence"].update(show_when_idle=self.show_idle.get(), language=self._lang_code())
        cfg["app"]["autostart"] = self.autostart.get()
        return cfg

    def _set_pill(self, text: str, color: str) -> None:
        self.pill.configure(text=f"   ●  {text}   ", text_color=color)

    # Discovery -------------------------------------------------------------

    def search(self) -> None:
        if self.searching:
            return
        self.searching = True
        self.find_btn.configure(state="disabled", text="🔍  Ищу…")
        self.find_info.configure(text="Слушаю сеть ~8 секунд", text_color=MUTED)
        self.found_menu.grid_forget()
        threading.Thread(target=lambda: self.events.put(("found", discover(8.0))), daemon=True).start()

    def _on_found(self, printers: list[FoundPrinter]) -> None:
        self.searching = False
        running = self.runner is not None and self.runner.running
        self.find_btn.configure(state="disabled" if running else "normal", text="🔍  Найти принтер в сети")
        self.found = printers
        if not printers:
            self.find_info.configure(
                text="Не нашёл. Проверь, что ПК и принтер в одной сети,\n"
                     "и разреши программу в брандмауэре Windows.", text_color=AMBER)
            return
        self.find_info.configure(text=f"Найдено принтеров: {len(printers)}", text_color=GREEN)
        if len(printers) > 1:
            self.found_menu.configure(values=[p.title for p in printers])
            self.found_menu.set(printers[0].title)
            self.found_menu.grid(row=2, column=0, sticky="ew", padx=16, pady=(4, 0))
        if not running:
            self._apply_found(printers[0])

    def _choose_found(self, title: str) -> None:
        for p in self.found:
            if p.title == title:
                self._apply_found(p)

    def _apply_found(self, p: FoundPrinter) -> None:
        self.cfg["printer"]["model_code"] = p.model_code
        self.f_host.set(p.host)
        self.f_serial.set(p.serial)
        self.f_name.entry.configure(placeholder_text=self._auto_name(p.serial))
        if not self.f_name.get():
            self.f_name.set("")  # refresh the placeholder
        self._show_preview(None)
        log.info("Выбран принтер: %s", p.title)
        if not self.f_code.get():
            self.tabs.set("Настройки")
            self.f_code.entry.focus_set()

    # Start / stop ----------------------------------------------------------

    def toggle(self) -> None:
        if self.runner and self.runner.running:
            self.stop()
        else:
            self.start()

    def start(self) -> None:
        cfg = self._collect()
        settings.save(cfg)
        try:
            validate(cfg)
        except ValueError as e:
            self.tabs.set("Настройки")
            self._set_pill("Заполни настройки", AMBER)
            self.find_info.configure(text=str(e), text_color=AMBER)
            log.warning("%s", e)
            return
        self.runner = Runner(cfg, on_status=lambda s, d: self.events.put(("status", (s, d))))
        self.runner.start()
        self._set_inputs_enabled(False)
        self.button.configure(text="■   Остановить", fg_color=RED, hover_color=RED_HOVER)
        self._set_pill("Подключение…", AMBER)
        self.tabs.set("Главная")
        log.info("Запущено")

    def stop(self) -> None:
        if self.runner:
            self.runner.stop(timeout=0)
        self.button.configure(text="Останавливаю…", state="disabled")

    def on_close(self) -> None:
        settings.save(self._collect())
        if self.runner:
            self.runner.stop(timeout=3)
        self.root.destroy()

    # Live view -------------------------------------------------------------

    def _show_preview(self, status: PrinterStatus | None) -> None:
        name = self._printer_name()
        activity = build_activity(status, name, self._lang_code()) if status else None
        self.pv_title.configure(text=name)
        if activity is None:
            self.pv_image.configure(image=self.art.get(None))
            self.pv_details.configure(text="Нажми «Запустить» внизу" if status is None
                                      else "Статус скрыт — принтер не на связи")
            self.pv_state.configure(text="")
            self.pv_time.configure(text="")
            return
        self.pv_image.configure(image=self.art.get(activity.get("small_image")))
        self.pv_details.configure(text=activity["details"].strip())
        self.pv_state.configure(text=activity.get("state", "").strip())
        left = status.remaining_min if activity.get("end") else None
        self.pv_time.configure(text=f"⏱  осталось {fmt_minutes(left)}" if left else "")

    def _show_stats(self, s: PrinterStatus) -> None:
        color = STATE_COLORS[s.state]
        if s.state == State.OFFLINE:
            self.st_job.configure(text="Нет связи с принтером" if self.runner else "Не запущено")
        else:
            self.st_job.configure(text="Калибровка" if s.calibration else (s.job_name or "Без задания"))
        pct = s.progress if s.state != State.OFFLINE else None
        self.st_percent.configure(text=f"{pct}%" if pct is not None else "", text_color=color)
        self.st_bar.configure(progress_color=color)
        self.st_bar.set((pct or 0) / 100)
        self.tiles["layer"].configure(text=f"{s.layer}/{s.total_layers}" if s.total_layers else "—")
        self.tiles["left"].configure(text=fmt_minutes(s.remaining_min) if s.state == State.PRINTING else "—")
        self.tiles["nozzle"].configure(text=f"{s.nozzle_temp:.0f}°" if s.nozzle_temp is not None else "—")
        self.tiles["bed"].configure(text=f"{s.bed_temp:.0f}°" if s.bed_temp is not None else "—")

    def _on_status(self, status: PrinterStatus, discord_ok: bool) -> None:
        if not (self.runner and self.runner.running):
            return
        self._show_preview(status)
        self._show_stats(status)
        if status.state == State.OFFLINE:
            self._set_pill("Нет связи с принтером", AMBER)
        elif not discord_ok:
            self._set_pill("Discord не запущен", AMBER)
        else:
            self._set_pill("Работает", GREEN)

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
        except queue.Empty:
            pass
        if self.runner and not self.runner.running:
            self.runner = None
            self.button.configure(text="▶   Запустить", state="normal", fg_color=GREEN, hover_color=GREEN_HOVER)
            self._set_inputs_enabled(True)
            self._set_pill("Остановлено", MUTED)
            self._show_preview(None)
            self._show_stats(PrinterStatus())
        self.root.after(200, self._poll)

    def _append_log(self, line: str) -> None:
        self.log_box.configure(state="normal")
        self.log_box.insert("end", line + "\n")
        if int(self.log_box.index("end-1c").split(".")[0]) > 500:
            self.log_box.delete("1.0", "100.0")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")


def main() -> None:
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("green")
    root = ctk.CTk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
