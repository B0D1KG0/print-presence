"""Background loop that moves printer status into Discord. Used by the CLI and the GUI."""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable

from .presence import DiscordPresence, build_activity, client_id_from
from .printers import create_printer
from .status import PrinterStatus, State

log = logging.getLogger(__name__)

# Discord rate-limits presence updates to about one per 15 seconds.
MIN_INTERVAL_S = 15

StatusCallback = Callable[[PrinterStatus, bool], None]


def validate(cfg: dict[str, Any]) -> None:
    """Raise ValueError with a human-readable message if settings are incomplete."""
    if not client_id_from(cfg):
        raise ValueError("Не указан Discord Application ID")
    create_printer(cfg.get("printer", {}))  # validates printer fields


class Runner:
    def __init__(self, cfg: dict[str, Any], on_status: StatusCallback | None = None) -> None:
        validate(cfg)
        self.cfg = cfg
        self.on_status = on_status
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="print-presence", daemon=True)
        self._thread.start()

    def stop(self, timeout: float | None = 5) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout)

    def run_forever(self) -> None:
        """Run in the current thread until stop() is called (or Ctrl+C)."""
        self._run()

    def _run(self) -> None:
        try:
            self._loop()
        except Exception:
            log.exception("Непредвиденная ошибка")

    def _loop(self) -> None:
        cfg = self.cfg
        opts = cfg.get("presence", {})
        lang = opts.get("language", "ru")
        show_idle = opts.get("show_when_idle", True)
        interval = max(MIN_INTERVAL_S, int(opts.get("update_interval", MIN_INTERVAL_S)))

        printer = create_printer(cfg.get("printer", {}))
        discord = DiscordPresence(client_id_from(cfg))
        printer.start()
        try:
            # First update after a short pause so the printer has time to answer.
            wait = 3.0
            while not self._stop.wait(wait):
                wait = interval
                status = printer.status()
                activity = None
                if status.state != State.IDLE or show_idle:
                    activity = build_activity(status, printer.name, lang)
                discord.set(activity)
                if self.on_status:
                    self.on_status(status, discord.connected)
        finally:
            discord.close()
            printer.stop()
            log.info("Остановлено")
