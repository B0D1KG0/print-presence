"""Settings for the GUI, stored as JSON in the user's AppData folder."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

DEFAULTS: dict[str, Any] = {
    "discord": {"use_default": True, "client_id": ""},
    "printers": [],
    "presence": {"language": "auto", "show_when_idle": True, "hide_job": False, "button": True},
    "app": {"autostart": False, "language": "auto", "close_to_tray": True, "check_updates": True},
}

EMPTY_PRINTER: dict[str, Any] = {"type": "bambu", "name": "", "host": "", "access_code": "", "serial": ""}


# A file with this name next to PrintPresence.exe turns on portable mode:
# settings and the picture cache are kept in a "data" folder next to the exe.
PORTABLE_MARKER = "portable.txt"


def app_dir() -> Path | None:
    """Folder of the running exe (None when running from source)."""
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else None


def is_portable(exe_dir: Path | None = None) -> bool:
    exe_dir = exe_dir or app_dir()
    return exe_dir is not None and (exe_dir / PORTABLE_MARKER).exists()


def data_dir(exe_dir: Path | None = None) -> Path:
    exe_dir = exe_dir or app_dir()
    if exe_dir is not None and is_portable(exe_dir):
        return exe_dir / "data"
    base = os.environ.get("APPDATA") or Path.home() / ".config"
    return Path(base) / "PrintPresence"


def settings_path() -> Path:
    return data_dir() / "settings.json"


def load(path: Path | None = None) -> dict[str, Any]:
    path = path or settings_path()
    cfg = json.loads(json.dumps(DEFAULTS))  # deep copy
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return cfg
    for section, values in stored.items():
        if isinstance(values, dict):
            cfg.setdefault(section, {}).update(values)
        elif section == "printers" and isinstance(values, list):
            cfg["printers"] = [dict(EMPTY_PRINTER, **p) for p in values if isinstance(p, dict)]
    migrate(cfg)
    return cfg


def migrate(cfg: dict[str, Any]) -> dict[str, Any]:
    """v0.5 stored a single [printer]; now there is a list of printers."""
    old = cfg.pop("printer", None)
    if not cfg.get("printers") and isinstance(old, dict) and any(old.get(k) for k in ("host", "serial")):
        cfg["printers"] = [dict(EMPTY_PRINTER, **old)]
    cfg.setdefault("printers", [])
    return cfg


def save(cfg: dict[str, Any], path: Path | None = None) -> None:
    path = path or settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
