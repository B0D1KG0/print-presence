"""Settings for the GUI, stored as JSON in the user's AppData folder."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULTS: dict[str, Any] = {
    "discord": {"use_default": True, "client_id": ""},
    "printer": {"type": "bambu", "name": "", "host": "", "access_code": "", "serial": ""},
    "presence": {"language": "auto", "show_when_idle": True},
    "app": {"autostart": False, "language": "auto"},
}


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
    return cfg


def save(cfg: dict[str, Any], path: Path | None = None) -> None:
    path = path or settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
