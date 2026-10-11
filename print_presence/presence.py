"""Turns PrinterStatus into a Discord activity and keeps it updated."""

from __future__ import annotations

import logging
import time
from typing import Any

from pypresence import Presence
from pypresence.exceptions import PyPresenceException

from .filament import filament_label
from .i18n import tr
from .status import PrinterStatus, State

log = logging.getLogger(__name__)

# Shared "Print Presence" Discord application with the art assets already uploaded.
# Application IDs are public, so it's fine to ship it. Users can override it in settings.
DEFAULT_CLIENT_ID = "700742403417702491"


def client_id_from(cfg: dict[str, Any]) -> str:
    """Shared app unless the user switched to their own; empty string if their own ID is missing."""
    discord = cfg.get("discord", {})
    custom = str(discord.get("client_id", "")).strip()
    if discord.get("use_default", not custom):
        return DEFAULT_CLIENT_ID
    return custom


REPO_URL = "https://github.com/B0D1KG0/print-presence"

TEXTS = {
    "ru": {
        State.IDLE: "Простаивает",
        State.PREPARING: "Готовится к печати",
        State.PRINTING: "Печатает",
        State.PAUSED: "Пауза",
        State.FINISHED: "Печать завершена",
        State.FAILED: "Печать прервана",
        "layer": "Слой",
        "nozzle": "Сопло",
        "bed": "Стол",
        "calibration": "Калибровка",
        "button": "Скачать Print Presence",
    },
    "uk": {
        State.IDLE: "Простоює",
        State.PREPARING: "Готується до друку",
        State.PRINTING: "Друкує",
        State.PAUSED: "Пауза",
        State.FINISHED: "Друк завершено",
        State.FAILED: "Друк перервано",
        "layer": "Шар",
        "nozzle": "Сопло",
        "bed": "Стіл",
        "calibration": "Калібрування",
        "button": "Завантажити Print Presence",
    },
    "en": {
        State.IDLE: "Idle",
        State.PREPARING: "Preparing",
        State.PRINTING: "Printing",
        State.PAUSED: "Paused",
        State.FINISHED: "Print finished",
        State.FAILED: "Print failed",
        "layer": "Layer",
        "nozzle": "Nozzle",
        "bed": "Bed",
        "calibration": "Calibration",
        "button": "Get Print Presence",
    },
}

# Asset keys uploaded in Discord Developer Portal -> Rich Presence -> Art Assets.
SMALL_IMAGES = {
    State.IDLE: "idle",
    State.PREPARING: "printing",
    State.PRINTING: "printing",
    State.PAUSED: "paused",
    State.FINISHED: "finished",
    State.FAILED: "failed",
}


def _clip(text: str) -> str:
    # Discord requires 2..128 characters for details/state.
    text = text.strip()
    if len(text) > 128:
        text = text[:127] + "…"
    return text.ljust(2)


def build_activity(
    status: PrinterStatus,
    printer_name: str,
    lang: str = "ru",
    now: float | None = None,
    large_image: str = "printer",
    hide_job: bool = False,
    button: bool = True,
) -> dict[str, Any] | None:
    """Return pypresence.update() kwargs, or None to clear the presence."""
    if status.state == State.OFFLINE:
        return None
    t = TEXTS.get(lang, TEXTS["en"])
    now = time.time() if now is None else now
    job = t["calibration"] if status.calibration else (status.job_name or "")
    if hide_job and not status.calibration:
        job = ""

    details = t[status.state]
    if job and status.state in (State.PRINTING, State.PAUSED):
        details = f"{details}: {job}"

    state = None
    if status.state in (State.PRINTING, State.PAUSED):
        parts = []
        if status.layer is not None and status.total_layers:
            parts.append(f"{t['layer']} {status.layer}/{status.total_layers}")
        if status.progress is not None:
            parts.append(f"{status.progress}%")
        state = " · ".join(parts) or None
    elif job and status.state in (State.PREPARING, State.FINISHED, State.FAILED):
        state = job

    temps = []
    if status.nozzle_temp is not None:
        temps.append(f"{t['nozzle']} {status.nozzle_temp:.0f}°C")
    if status.bed_temp is not None:
        temps.append(f"{t['bed']} {status.bed_temp:.0f}°C")

    activity: dict[str, Any] = {
        "name": printer_name,
        "details": _clip(details),
        "large_image": large_image,
        "large_text": _clip(" · ".join(p for p in (
            printer_name, filament_label(status.filament, status.filament_color, lang)) if p)),
        "small_image": SMALL_IMAGES[status.state],
        "small_text": " · ".join(temps) or t[status.state],
    }
    if state:
        activity["state"] = _clip(state)
    if button:
        # Discord shows buttons to other people only, never on your own profile.
        activity["buttons"] = [{"label": t["button"], "url": REPO_URL}]
    if status.state == State.PRINTING and status.remaining_min:
        # Round to a minute so the timestamp doesn't jitter between updates.
        activity["end"] = int((now + status.remaining_min * 60) // 60 * 60)
    return activity


def _summary(activity: dict[str, Any] | None) -> str:
    if not activity:
        return tr("log.presence_hidden")
    return " · ".join(activity[k].strip() for k in ("details", "state") if activity.get(k))


class DiscordPresence:
    """Wraps pypresence with automatic (re)connection to the Discord client."""

    def __init__(self, client_id: str) -> None:
        self.client_id = client_id
        self._rpc: Presence | None = None
        self._last: dict[str, Any] | None = None
        self._next_connect = 0.0

    @property
    def connected(self) -> bool:
        return self._rpc is not None

    def _connect(self) -> bool:
        if self._rpc is not None:
            return True
        if time.monotonic() < self._next_connect:
            return False
        try:
            rpc = Presence(self.client_id)
            rpc.connect()
        except Exception as e:  # pypresence raises a zoo of errors when Discord is closed
            log.warning(tr("log.discord_unavailable", error=e))
            self._next_connect = time.monotonic() + 30
            return False
        log.info(tr("log.discord_connected"))
        self._rpc = rpc
        self._last = None
        return True

    def _drop(self, error: Exception) -> None:
        log.warning(tr("log.discord_lost", error=error))
        try:
            if self._rpc:
                self._rpc.close()
        except Exception:
            pass
        self._rpc = None

    def set(self, activity: dict[str, Any] | None) -> None:
        if not self._connect() or activity == self._last:
            return
        assert self._rpc is not None
        try:
            if activity is None:
                self._rpc.clear()
            else:
                self._rpc.update(**activity)
        except (PyPresenceException, OSError) as e:
            self._drop(e)
            return
        self._last = activity
        log.info(tr("log.presence", summary=_summary(activity)))

    def close(self) -> None:
        if self._rpc is None:
            return
        try:
            self._rpc.clear()
            self._rpc.close()
        except Exception:
            pass
        self._rpc = None
