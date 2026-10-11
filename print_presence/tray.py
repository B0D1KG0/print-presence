"""System tray icon (pystray). Menu callbacks are forwarded to the GUI thread through a queue."""

from __future__ import annotations

import logging
import queue
from typing import Callable

from PIL import Image

from .i18n import tr

log = logging.getLogger(__name__)


class Tray:
    def __init__(self, image: Image.Image, events: queue.Queue, is_running: Callable[[], bool]) -> None:
        self.events = events
        self.is_running = is_running
        self.icon = None
        try:
            import pystray

            item = pystray.MenuItem
            menu = pystray.Menu(
                item(tr("tray.open"), lambda: self.events.put(("tray", "open")), default=True),
                item(lambda _: tr("tray.stop") if self.is_running() else tr("tray.start"),
                     lambda: self.events.put(("tray", "toggle"))),
                pystray.Menu.SEPARATOR,
                item(tr("tray.quit"), lambda: self.events.put(("tray", "quit"))),
            )
            self.icon = pystray.Icon("PrintPresence", image.resize((64, 64)), "Print Presence", menu)
            self.icon.run_detached()
        except Exception as e:  # no tray on this system: the window just closes normally
            log.debug("Tray unavailable: %s", e)
            self.icon = None

    @property
    def available(self) -> bool:
        return self.icon is not None

    def set_tooltip(self, text: str) -> None:
        if self.icon is not None:
            try:
                self.icon.title = text[:127]
                self.icon.update_menu()
            except Exception:
                pass

    def stop(self) -> None:
        if self.icon is not None:
            try:
                self.icon.stop()
            except Exception:
                pass
