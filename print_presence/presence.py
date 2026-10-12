"""Turns PrinterStatus into a Discord activity and keeps it updated."""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from pypresence import Presence
from pypresence.exceptions import PyPresenceException

from .filament import color_name, filament_label
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
# Discord limits button labels to 32 *bytes*: a longer (e.g. Cyrillic) label makes the server
# silently drop the whole activity for other people while it still shows on your own profile.
BUTTON_LABEL = "Get Print Presence"

TEXTS = {
    "ru": {
        State.IDLE: "Простаивает",
        State.PREPARING: "Готовится к печати",
        State.PRINTING: "Печатает",
        State.PAUSED: "Пауза",
        State.FINISHED: "Печать завершена",
        State.FAILED: "Печать прервана",
        "layer": "Слой",
        "hm": "{h} ч {m} мин",
        "m": "{m} мин",
        "nozzle": "Сопло",
        "bed": "Стол",
        "calibration": "Калибровка",
    },
    "uk": {
        State.IDLE: "Простоює",
        State.PREPARING: "Готується до друку",
        State.PRINTING: "Друкує",
        State.PAUSED: "Пауза",
        State.FINISHED: "Друк завершено",
        State.FAILED: "Друк перервано",
        "layer": "Шар",
        "hm": "{h} год {m} хв",
        "m": "{m} хв",
        "nozzle": "Сопло",
        "bed": "Стіл",
        "calibration": "Калібрування",
    },
    "en": {
        State.IDLE: "Idle",
        State.PREPARING: "Preparing",
        State.PRINTING: "Printing",
        State.PAUSED: "Paused",
        State.FINISHED: "Print finished",
        State.FAILED: "Print failed",
        "layer": "Layer",
        "hm": "{h}h {m}m",
        "m": "{m}m",
        "nozzle": "Nozzle",
        "bed": "Bed",
        "calibration": "Calibration",
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


# Rich Presence constructor -------------------------------------------------------
#
# Each line of the status is a template: {name} is replaced with a value, and a part in
# [square brackets] disappears when any value inside it is empty, e.g. "{status}[: {job}]".

TEMPLATE_KEYS = ("details", "state", "large_text", "small_text")
DEFAULT_TEMPLATES: dict[str, Any] = {
    "enabled": False,
    "details": "{status}[: {job}]",
    "state": "[{layer}][ · {progress}]",
    "large_text": "{printer}[ · {filament}]",
    "small_text": "{temps}",
    "timer": True,
}
VARIABLES = ("status", "job", "layer", "progress", "remaining", "eta", "filament", "material", "color",
             "nozzle", "bed", "temps", "printer", "layer_num", "total_layers")

_GROUP = re.compile(r"\[([^\[\]]*)\]")
_FIELD = re.compile(r"\{(\w+)\}")
_SEPARATORS = " ·|:,–—"


def custom_options(presence: dict[str, Any] | None) -> dict[str, Any]:
    """Constructor settings with the defaults filled in."""
    stored = (presence or {}).get("custom")
    opts = dict(DEFAULT_TEMPLATES)
    if isinstance(stored, dict):
        opts.update({k: v for k, v in stored.items() if k in DEFAULT_TEMPLATES})
    return opts


def render_template(template: str, values: dict[str, str]) -> str:
    """Fill a template; unknown {names} stay as typed so a typo is easy to spot."""

    def fill(text: str) -> tuple[str, bool]:
        empty = False

        def sub(m: re.Match) -> str:
            nonlocal empty
            if m.group(1) not in values:
                return m.group(0)
            value = values[m.group(1)]
            if not value:
                empty = True
            return value or ""

        return _FIELD.sub(sub, text), empty

    def group(m: re.Match) -> str:
        text, empty = fill(m.group(1))
        return "" if empty else text

    text, _ = fill(_GROUP.sub(group, template or ""))
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s*([·|])(\s*[·|])+\s*", r" \1 ", text)  # separators left around empty values
    return text.strip(_SEPARATORS)


def _duration(minutes: int, t: dict) -> str:
    h, m = divmod(int(minutes), 60)
    return t["hm"].format(h=h, m=m) if h else t["m"].format(m=m)


def template_values(status: PrinterStatus, printer_name: str, lang: str = "en", now: float | None = None,
                    hide_job: bool = False) -> dict[str, str]:
    """Values for the constructor variables; print progress is only filled while printing or paused."""
    t = TEXTS.get(lang, TEXTS["en"])
    now = time.time() if now is None else now
    s = status
    active = s.state in (State.PRINTING, State.PAUSED)
    job = t["calibration"] if s.calibration else ("" if hide_job else s.job_name or "")
    if s.state not in (State.PREPARING, State.PRINTING, State.PAUSED, State.FINISHED, State.FAILED):
        job = ""
    has_layers = active and s.layer is not None and bool(s.total_layers)
    remaining = active and bool(s.remaining_min)
    nozzle = f"{s.nozzle_temp:.0f}°C" if s.nozzle_temp is not None else ""
    bed = f"{s.bed_temp:.0f}°C" if s.bed_temp is not None else ""
    temps = " · ".join(f"{t[k]} {v}" for k, v in (("nozzle", nozzle), ("bed", bed)) if v)
    return {
        "status": t.get(s.state, ""),
        "job": job,
        "layer": f"{t['layer']} {s.layer}/{s.total_layers}" if has_layers else "",
        "layer_num": str(s.layer) if has_layers else "",
        "total_layers": str(s.total_layers) if has_layers else "",
        "progress": f"{s.progress}%" if active and s.progress is not None else "",
        "remaining": _duration(s.remaining_min, t) if remaining else "",
        "eta": time.strftime("%H:%M", time.localtime(now + s.remaining_min * 60)) if remaining else "",
        "filament": filament_label(s.filament, s.filament_color, lang) or "",
        "material": s.filament or "",
        "color": color_name(s.filament_color, lang) or "",
        "nozzle": nozzle,
        "bed": bed,
        "temps": temps,
        "printer": printer_name or "",
    }


def _custom_activity(status: PrinterStatus, printer_name: str, lang: str, now: float, large_image: str,
                     hide_job: bool, button: bool, custom: dict[str, Any]) -> dict[str, Any]:
    values = template_values(status, printer_name, lang, now, hide_job)
    lines = {k: render_template(str(custom.get(k, "")), values) for k in TEMPLATE_KEYS}
    activity: dict[str, Any] = {
        "name": printer_name,
        "details": _clip(lines["details"] or values["status"]),
        "large_image": large_image,
        "small_image": SMALL_IMAGES[status.state],
        "small_text": lines["small_text"] or values["status"],
    }
    if lines["state"]:
        activity["state"] = _clip(lines["state"])
    if lines["large_text"]:
        activity["large_text"] = _clip(lines["large_text"])
    if button:
        activity["buttons"] = [{"label": BUTTON_LABEL, "url": REPO_URL}]
    if custom.get("timer", True) and status.state == State.PRINTING and status.remaining_min:
        activity["end"] = int((now + status.remaining_min * 60) // 60 * 60)
    return activity


def build_activity(
    status: PrinterStatus,
    printer_name: str,
    lang: str = "ru",
    now: float | None = None,
    large_image: str = "printer",
    hide_job: bool = False,
    button: bool = True,
    custom: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Return pypresence.update() kwargs, or None to clear the presence.

    custom: constructor settings (see DEFAULT_TEMPLATES); used when custom["enabled"] is set.
    """
    if status.state == State.OFFLINE:
        return None
    now = time.time() if now is None else now
    if custom and custom.get("enabled"):
        return _custom_activity(status, printer_name, lang, now, large_image, hide_job, button, custom)
    t = TEXTS.get(lang, TEXTS["en"])
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
        activity["buttons"] = [{"label": BUTTON_LABEL, "url": REPO_URL}]
    if status.state == State.PRINTING and status.remaining_min:
        # Round to a minute so the timestamp doesn't jitter between updates.
        activity["end"] = int((now + status.remaining_min * 60) // 60 * 60)
    return activity


def _summary(activity: dict[str, Any] | None) -> str:
    if not activity:
        return tr("log.presence_hidden")
    return " · ".join(activity[k].strip() for k in ("details", "state") if activity.get(k))


def discord_payload(activity: dict[str, Any]) -> dict[str, Any]:
    """What is actually sent to Discord.

    "name" is only used by the app's own preview: Discord shows the activity locally with it,
    but doesn't pass such an activity on to other people. The status title always comes from
    the Discord application name.
    """
    return {k: v for k, v in activity.items() if k != "name"}


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
                self._rpc.update(**discord_payload(activity))
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
