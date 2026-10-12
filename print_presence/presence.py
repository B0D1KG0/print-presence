"""Turns PrinterStatus into a Discord activity and keeps it updated."""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from pypresence import Presence
from pypresence.exceptions import PyPresenceException
from pypresence.types import ActivityType, StatusDisplayType

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
# Parts of the status that can be switched off; the first line is always shown.
HIDEABLE = ("state", "large_text", "small_text", "small_image")
# States that can have their own text; the others (preparing) use the main templates.
OVERRIDE_STATES = (State.PRINTING, State.PAUSED, State.FINISHED, State.FAILED, State.IDLE)
TIMERS = ("remaining", "elapsed", "none")
PARTIES = ("none", "layers", "progress")
ACTIVITY_TYPES = (0, 3, 2, 5)  # Playing, Watching, Listening, Competing — the ones Discord supports
STATUS_DISPLAYS = ("name", "details", "state")  # what the member list shows after "Playing"
BUTTON_LIMIT = 32  # bytes
DEFAULT_TEMPLATES: dict[str, Any] = {
    "enabled": False,
    "details": "{status}[: {job}]",
    "state": "[{layer}][ · {progress}]",
    "large_text": "{printer}[ · {filament}]",
    "small_text": "{temps}",
    "overrides": {},  # state -> its own {details, state, large_text, small_text}
    "hidden": [],
    "timer": "remaining",
    "party": "none",
    "activity_type": 0,
    "status_display": "name",
    "button_on": False,
    "button_label": "",
    "button_url": "",
}
VARIABLES = ("status", "job", "layer", "progress", "remaining", "eta", "filament", "material", "color",
             "nozzle", "bed", "temps", "printer", "layer_num", "total_layers")

_GROUP = re.compile(r"\[([^\[\]]*)\]")
_FIELD = re.compile(r"\{(\w+)\}")
_SEPARATORS = " ·|:,–—"


def custom_options(presence: dict[str, Any] | None) -> dict[str, Any]:
    """Constructor settings with the defaults filled in."""
    stored = (presence or {}).get("custom")
    opts = json.loads(json.dumps(DEFAULT_TEMPLATES))  # deep copy
    if isinstance(stored, dict):
        opts.update({k: v for k, v in stored.items() if k in DEFAULT_TEMPLATES})
    if isinstance(opts["timer"], bool):  # v0.9.0 had an on/off switch
        opts["timer"] = "remaining" if opts["timer"] else "none"
    if opts["timer"] not in TIMERS:
        opts["timer"] = "remaining"
    if opts["party"] not in PARTIES:
        opts["party"] = "none"
    if opts["activity_type"] not in ACTIVITY_TYPES:
        opts["activity_type"] = 0
    if opts["status_display"] not in STATUS_DISPLAYS:
        opts["status_display"] = "name"
    if not isinstance(opts["overrides"], dict):
        opts["overrides"] = {}
    opts["overrides"] = {k: v for k, v in opts["overrides"].items()
                         if k in {st.value for st in OVERRIDE_STATES} and isinstance(v, dict)}
    if not isinstance(opts["hidden"], list):
        opts["hidden"] = []
    return opts


def templates_for(custom: dict[str, Any], state: State) -> dict[str, str]:
    """Line templates used for this printer state (its own ones, if set)."""
    own = (custom.get("overrides") or {}).get(state.value)
    source = own if isinstance(own, dict) else custom
    return {k: str(source.get(k, custom.get(k, "")) or "") for k in TEMPLATE_KEYS}


def fit_bytes(text: str, limit: int = BUTTON_LIMIT) -> str:
    """Cut text to Discord's byte limit without breaking a character."""
    data = text.encode("utf-8")
    if len(data) <= limit:
        return text
    return data[:limit].decode("utf-8", "ignore").rstrip()


def valid_url(url: str) -> bool:
    return bool(re.fullmatch(r"https?://[^\s/$.?#][^\s]*", url or "")) and len(url) <= 512


class PrintClock:
    """Remembers when the current print started — the printer doesn't report it.

    If the app starts in the middle of a print, the start is estimated from progress and time left.
    """

    def __init__(self) -> None:
        self.job: str | None = None
        self.start: float | None = None

    def update(self, status: PrinterStatus, now: float | None = None) -> float | None:
        now = time.time() if now is None else now
        if status.state not in (State.PRINTING, State.PAUSED):
            if status.state != State.OFFLINE:  # a short connection drop keeps the clock
                self.job, self.start = None, None
            return None
        if self.start is None or status.job_name != self.job:
            self.job = status.job_name
            elapsed = 0.0
            if status.progress and status.remaining_min and status.progress < 100:
                elapsed = status.remaining_min * status.progress / (100 - status.progress)
            self.start = (now - elapsed * 60) // 60 * 60
        return self.start


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


def render_lines(status: PrinterStatus, printer_name: str, lang: str, custom: dict[str, Any],
                 now: float | None = None, hide_job: bool = False) -> dict[str, str]:
    """Rendered text of every line (before Discord's limits are applied)."""
    values = template_values(status, printer_name, lang, now, hide_job)
    lines = {k: render_template(v, values) for k, v in templates_for(custom, status.state).items()}
    lines["button_label"] = render_template(str(custom.get("button_label", "")), values)
    return lines


def _custom_activity(status: PrinterStatus, printer_name: str, lang: str, now: float, large_image: str,
                     hide_job: bool, button: bool, custom: dict[str, Any],
                     started: float | None) -> dict[str, Any]:
    t = TEXTS.get(lang, TEXTS["en"])
    lines = render_lines(status, printer_name, lang, custom, now, hide_job)
    hidden = set(custom.get("hidden") or ())
    activity: dict[str, Any] = {
        "name": printer_name,
        "details": _clip(lines["details"] or t[status.state]),
        "large_image": large_image,
    }
    if "small_image" not in hidden:
        activity["small_image"] = SMALL_IMAGES[status.state]
        if "small_text" not in hidden:
            activity["small_text"] = _clip(lines["small_text"] or t[status.state])
    if lines["state"] and "state" not in hidden:
        activity["state"] = _clip(lines["state"])
    if lines["large_text"] and "large_text" not in hidden:
        activity["large_text"] = _clip(lines["large_text"])

    buttons = []
    label = fit_bytes(lines["button_label"].strip())
    if custom.get("button_on") and label and valid_url(str(custom.get("button_url", "")).strip()):
        buttons.append({"label": label, "url": str(custom["button_url"]).strip()})
    if button:
        buttons.append({"label": BUTTON_LABEL, "url": REPO_URL})
    if buttons:
        activity["buttons"] = buttons[:2]

    printing = status.state == State.PRINTING
    timer = custom.get("timer", "remaining")
    if timer == "remaining" and printing and status.remaining_min:
        activity["end"] = int((now + status.remaining_min * 60) // 60 * 60)
    elif timer == "elapsed" and printing and started:
        activity["start"] = int(started)

    party = custom.get("party", "none")
    if status.state in (State.PRINTING, State.PAUSED):
        size = None
        if party == "layers" and status.layer and status.total_layers and status.layer <= status.total_layers:
            size = [status.layer, status.total_layers]
        elif party == "progress" and status.progress and 0 < status.progress <= 100:
            size = [status.progress, 100]
        if size:
            activity["party_id"] = "print-presence"
            activity["party_size"] = size
    if custom.get("activity_type", 0) in ACTIVITY_TYPES[1:]:
        activity["activity_type"] = custom["activity_type"]
    if custom.get("status_display") in ("details", "state"):
        activity["status_display_type"] = custom["status_display"]
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
    started: float | None = None,
) -> dict[str, Any] | None:
    """Return pypresence.update() kwargs, or None to clear the presence.

    custom: constructor settings (see DEFAULT_TEMPLATES); used when custom["enabled"] is set.
    started: when the current print started (PrintClock), for the "elapsed" timer.
    """
    if status.state == State.OFFLINE:
        return None
    now = time.time() if now is None else now
    if custom and custom.get("enabled"):
        return _custom_activity(status, printer_name, lang, now, large_image, hide_job, button, custom, started)
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
    payload = {k: v for k, v in activity.items() if k != "name"}
    if "activity_type" in payload:
        payload["activity_type"] = ActivityType(payload["activity_type"])
    if "status_display_type" in payload:
        payload["status_display_type"] = {"state": StatusDisplayType.STATE,
                                          "details": StatusDisplayType.DETAILS}[payload["status_display_type"]]
    return payload


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
