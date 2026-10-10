from __future__ import annotations

from typing import Any

from .base import Printer


def create_printer(cfg: dict[str, Any]) -> Printer:
    kind = cfg.get("type", "bambu")
    if kind == "bambu":
        from .bambu import BambuPrinter
        from .bambu_discovery import display_name

        # Empty name = derive it from the model, e.g. "Bambu Lab P1S".
        name = str(cfg.get("name", "")).strip() or display_name(cfg.get("model_code"), cfg.get("serial"))

        for key in ("host", "serial", "access_code"):
            if not cfg.get(key):
                raise ValueError(f"[printer] {key} is not set in config.toml")
        return BambuPrinter(name, cfg["host"], cfg["serial"], cfg["access_code"])
    raise ValueError(f"Unknown printer type: {kind!r}")
