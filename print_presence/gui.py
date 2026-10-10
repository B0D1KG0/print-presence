"""Simple settings window with a Start/Stop button."""

from __future__ import annotations

import logging
import queue
import sys
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

from . import __version__, settings
from .presence import build_activity
from .runner import Runner, validate
from .status import PrinterStatus, State

log = logging.getLogger("print_presence")

DEV_PORTAL = "https://discord.com/developers/applications"
REPO_URL = "https://github.com/B0D1KG0/print-presence"

# (section, key, label, hint, secret)
FIELDS = [
    ("discord", "client_id", "Discord Application ID",
     "discord.com/developers → твоё приложение → General Information → Application ID", False),
    ("printer", "name", "Имя в Discord",
     "Так будет написано в профиле: «Играет в …»", False),
    ("printer", "host", "IP принтера",
     "На принтере: Настройки → WLAN → IP", False),
    ("printer", "access_code", "Access Code",
     "Там же: Настройки → WLAN → Access Code (8 символов)", True),
    ("printer", "serial", "Серийный номер",
     "Bambu Studio → Устройство → Обновление (Serial), или в настройках принтера", False),
]


def resource(name: str) -> Path:
    # Files bundled by PyInstaller live in sys._MEIPASS.
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / name


class QueueHandler(logging.Handler):
    def __init__(self, q: queue.Queue) -> None:
        super().__init__()
        self.q = q
        self.setFormatter(logging.Formatter("%(asctime)s  %(message)s", "%H:%M:%S"))

    def emit(self, record: logging.LogRecord) -> None:
        self.q.put(("log", self.format(record)))


def describe(status: PrinterStatus, name: str, lang: str) -> str:
    if status.state == State.OFFLINE:
        return "Принтер не подключён"
    activity = build_activity(status, name, lang) or {}
    return " · ".join(p.strip() for p in (activity.get("details"), activity.get("state")) if p)


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.cfg = settings.load()
        self.runner: Runner | None = None
        self.events: queue.Queue = queue.Queue()
        self.vars: dict[tuple[str, str], tk.StringVar] = {}

        handler = QueueHandler(self.events)
        logging.getLogger().addHandler(handler)
        logging.getLogger().setLevel(logging.INFO)

        root.title(f"Print Presence {__version__}")
        root.resizable(False, False)
        try:
            self._icon = tk.PhotoImage(file=resource("assets/printer.png")).subsample(8)
            root.iconphoto(True, self._icon)
        except tk.TclError:
            pass

        self._build()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.after(200, self._poll)
        if self.cfg["app"].get("autostart"):
            root.after(500, self.start)

    # UI --------------------------------------------------------------------

    def _build(self) -> None:
        frm = ttk.Frame(self.root, padding=16)
        frm.grid(sticky="nsew")
        frm.columnconfigure(1, weight=1)

        row = 0
        for section, key, label, hint, secret in FIELDS:
            var = tk.StringVar(value=str(self.cfg.get(section, {}).get(key, "")))
            self.vars[(section, key)] = var
            ttk.Label(frm, text=label, font=("Segoe UI", 10, "bold")).grid(row=row, column=0, sticky="w", pady=(8, 0))
            entry = ttk.Entry(frm, textvariable=var, width=42, show="•" if secret else "")
            entry.grid(row=row, column=1, sticky="ew", padx=(12, 0), pady=(8, 0))
            if secret:
                self.secret_entry = entry
                self.show_secret = tk.BooleanVar(value=False)
                ttk.Checkbutton(frm, text="показать", variable=self.show_secret,
                                command=self._toggle_secret).grid(row=row, column=2, padx=(8, 0), pady=(8, 0))
            if key == "client_id":
                ttk.Button(frm, text="Открыть", command=lambda: webbrowser.open(DEV_PORTAL)).grid(
                    row=row, column=2, padx=(8, 0), pady=(8, 0))
            row += 1
            ttk.Label(frm, text=hint, foreground="#6b7280", font=("Segoe UI", 8)).grid(
                row=row, column=1, columnspan=2, sticky="w", padx=(12, 0))
            row += 1

        opts = ttk.Frame(frm)
        opts.grid(row=row, column=0, columnspan=3, sticky="w", pady=(14, 0))
        self.show_idle = tk.BooleanVar(value=bool(self.cfg["presence"].get("show_when_idle", True)))
        self.autostart = tk.BooleanVar(value=bool(self.cfg["app"].get("autostart", False)))
        self.lang = tk.StringVar(value=self.cfg["presence"].get("language", "ru"))
        ttk.Checkbutton(opts, text="Показывать, когда принтер простаивает", variable=self.show_idle).pack(anchor="w")
        ttk.Checkbutton(opts, text="Включать сразу при запуске программы", variable=self.autostart).pack(anchor="w")
        lang_row = ttk.Frame(opts)
        lang_row.pack(anchor="w", pady=(4, 0))
        ttk.Label(lang_row, text="Язык статуса:").pack(side="left")
        ttk.Combobox(lang_row, textvariable=self.lang, values=["ru", "en"], width=5, state="readonly").pack(
            side="left", padx=(6, 0))
        row += 1

        self.button = ttk.Button(frm, text="▶  Запустить", command=self.toggle)
        self.button.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(16, 0), ipady=6)
        row += 1

        self.status_var = tk.StringVar(value="Остановлено")
        ttk.Label(frm, textvariable=self.status_var, font=("Segoe UI", 10)).grid(
            row=row, column=0, columnspan=3, sticky="w", pady=(10, 0))
        row += 1

        self.log_box = tk.Text(frm, height=7, width=70, state="disabled", font=("Consolas", 8),
                               background="#f3f4f6", relief="flat")
        self.log_box.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        row += 1

        links = ttk.Frame(frm)
        links.grid(row=row, column=0, columnspan=3, sticky="w", pady=(8, 0))
        ttk.Button(links, text="Инструкция", command=lambda: webbrowser.open(REPO_URL + "#readme")).pack(side="left")

        self.inputs = [w for w in frm.winfo_children() if isinstance(w, (ttk.Entry,))]

    def _toggle_secret(self) -> None:
        self.secret_entry.configure(show="" if self.show_secret.get() else "•")

    def _collect(self) -> dict[str, Any]:
        cfg = self.cfg
        for (section, key), var in self.vars.items():
            cfg.setdefault(section, {})[key] = var.get().strip()
        cfg["presence"]["show_when_idle"] = self.show_idle.get()
        cfg["presence"]["language"] = self.lang.get()
        cfg["app"]["autostart"] = self.autostart.get()
        return cfg

    def _set_inputs_enabled(self, enabled: bool) -> None:
        for w in self.inputs:
            w.configure(state="normal" if enabled else "disabled")

    # Actions ---------------------------------------------------------------

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
            messagebox.showwarning("Print Presence", str(e))
            return
        self.runner = Runner(cfg, on_status=lambda s, d: self.events.put(("status", (s, d))))
        self.runner.start()
        self._set_inputs_enabled(False)
        self.button.configure(text="■  Остановить")
        self.status_var.set("Подключаюсь к принтеру…")
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

    # Background events -----------------------------------------------------

    def _poll(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "log":
                    self._append_log(payload)
                elif kind == "status" and self.runner and self.runner.running:
                    status, discord_ok = payload
                    text = describe(status, self.cfg["printer"]["name"], self.lang.get())
                    if not discord_ok:
                        text += "   (Discord не запущен)"
                    self.status_var.set(text)
        except queue.Empty:
            pass
        if self.runner and not self.runner.running:
            self.runner = None
            self.button.configure(text="▶  Запустить", state="normal")
            self._set_inputs_enabled(True)
            self.status_var.set("Остановлено")
        self.root.after(200, self._poll)

    def _append_log(self, line: str) -> None:
        self.log_box.configure(state="normal")
        self.log_box.insert("end", line + "\n")
        if int(self.log_box.index("end-1c").split(".")[0]) > 300:
            self.log_box.delete("1.0", "50.0")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")


def main() -> None:
    root = tk.Tk()
    try:
        ttk.Style(root).theme_use("vista")
    except tk.TclError:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
