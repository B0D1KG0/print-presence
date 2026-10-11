"""Settings for the GUI, stored as JSON in the user's AppData folder."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULTS: dict[str, Any] = {
    "discord": {"use_default": True, "client_id": ""},
    "printers": [],
    "presence": {"language": "auto", "show_when_idle": True, "hide_job": False, "button": True},
    "app": {"autostart": False, "language": "auto", "close_to_tray": True, "check_updates": True},
}

EMPTY_PRINTER: dict[str, Any] = {"type": "bambu", "name": "", "host": "", "access_code": "", "serial": ""}


def settings_path() -> Path:
    base = os.environ.get("APPDATA") or Path.home() / ".config"
    return Path(base) / "PrintPresence" / "settings.json"


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
