"""Background loop that moves printer status into Discord. Used by the CLI and the GUI."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

from .i18n import LANGUAGES, resolve, tr
from .presence import DEFAULT_CLIENT_ID, DiscordPresence, build_activity, client_id_from, custom_options
from .printers import create_printer
from .settings import migrate
from .status import PrinterStatus, State

log = logging.getLogger(__name__)

# Discord rate-limits presence updates to about one per 15 seconds.
MIN_INTERVAL_S = 15
# Changes made in the constructor are sent right away, but Discord allows only
# about 5 updates per 20 seconds, so keep at least this gap between them.
LIVE_GAP_S = 4

# Which printer is shown in Discord when there are several: the busiest one.
PRIORITY = {
    State.PRINTING: 6,
    State.PAUSED: 5,
    State.PREPARING: 4,
    State.FAILED: 3,
    State.FINISHED: 3,
    State.IDLE: 1,
    State.OFFLINE: 0,
}

# (statuses of all printers, index of the one shown in Discord, Discord connected)
StatusCallback = Callable[[list[PrinterStatus], int, bool], None]


def printer_configs(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    return migrate(cfg)["printers"]


def validate(cfg: dict[str, Any]) -> None:
    """Raise ValueError with a human-readable message if settings are incomplete."""
    if not client_id_from(cfg):
        raise ValueError(tr("err.client_id"))
    printers = printer_configs(cfg)
    if not printers:
        raise ValueError(tr("err.no_printers"))
    for p in printers:
        create_printer(p)  # validates printer fields


def status_language(status_choice: str | None, ui_choice: str | None) -> str:
    """Language of the Discord status; "auto" means the same as the interface."""
    return resolve(status_choice if status_choice in LANGUAGES else ui_choice)


def presence_options(cfg: dict[str, Any]) -> dict[str, Any]:
    """What the status looks like; can be changed while running (see Runner.update_presence)."""
    opts = cfg.get("presence", {})
    return {
        "lang": status_language(opts.get("language"), cfg.get("app", {}).get("language")),
        "show_idle": opts.get("show_when_idle", True),
        "hide_job": opts.get("hide_job", False),
        "button": opts.get("button", True),
        "custom": custom_options(opts),
    }


def pick_featured(statuses: list[PrinterStatus], current: int = 0) -> int:
    """Index of the printer to show; keeps the current one while it's as busy as the busiest."""
    best = max(PRIORITY[s.state] for s in statuses)
    if 0 <= current < len(statuses) and PRIORITY[statuses[current].state] == best:
        return current
    return next(i for i, s in enumerate(statuses) if PRIORITY[s.state] == best)


class Runner:
    def __init__(self, cfg: dict[str, Any], on_status: StatusCallback | None = None) -> None:
        validate(cfg)
        self.cfg = cfg
        self.on_status = on_status
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._opts = presence_options(cfg)
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="print-presence", daemon=True)
        self._thread.start()

    def update_presence(self, cfg: dict[str, Any]) -> None:
        """Apply new status options (constructor, switches, language) without restarting."""
        self._opts = presence_options(cfg)
        self._wake.set()

    def stop(self, timeout: float | None = 5) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout)

    def run_forever(self) -> None:
        """Run in the current thread until stop() is called (or Ctrl+C)."""
        self._run()

    def _run(self) -> None:
        try:
            self._loop()
        except Exception:
            log.exception(tr("log.unexpected"))

    def _loop(self) -> None:
        cfg = self.cfg
        interval = max(MIN_INTERVAL_S, int(cfg.get("presence", {}).get("update_interval", MIN_INTERVAL_S)))

        configs = printer_configs(cfg)
        printers = [create_printer(p) for p in configs]
        client_id = client_id_from(cfg)
        discord = DiscordPresence(client_id)
        images = [self._large_image(client_id, p) for p in configs]
        featured = 0
        last_sent = 0.0
        for printer in printers:
            printer.start()
        try:
            # First update after a short pause so the printers have time to answer.
            next_poll = time.monotonic() + 3
            while True:
                changed = self._wake.wait(max(0.0, next_poll - time.monotonic()))
                if self._stop.is_set():
                    break
                if changed:
                    self._wake.clear()
                    gap = last_sent + LIVE_GAP_S - time.monotonic()
                    if gap > 0 and self._stop.wait(gap):
                        break
                    self._wake.clear()  # changes made during the gap are picked up now
                else:
                    next_poll = time.monotonic() + interval
                opts = self._opts
                statuses = [p.status() for p in printers]
                featured = pick_featured(statuses, featured)
                status = statuses[featured]
                activity = None
                if status.state != State.IDLE or opts["show_idle"]:
                    activity = build_activity(status, printers[featured].name, opts["lang"],
                                              large_image=images[featured], hide_job=opts["hide_job"],
                                              button=opts["button"], custom=opts["custom"])
                discord.set(activity)
                last_sent = time.monotonic()
                if self.on_status:
                    self.on_status(statuses, featured, discord.connected)
        finally:
            discord.close()
            for printer in printers:
                printer.stop()
            log.info(tr("log.stopped"))

    @staticmethod
    def _large_image(client_id: str, printer_cfg: dict[str, Any]) -> str:
        # The shared app has a picture per model; custom apps are only required to have "printer".
        if client_id != DEFAULT_CLIENT_ID or printer_cfg.get("type", "bambu") != "bambu":
            return "printer"
        from .printers.bambu_discovery import image_key

        return image_key(printer_cfg.get("model_code"), printer_cfg.get("serial"))
