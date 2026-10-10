from __future__ import annotations

from typing import Any

from .base import Printer


def create_printer(cfg: dict[str, Any]) -> Printer:
    kind = cfg.get("type", "bambu")
    name = cfg.get("name", "3D Printer")
    if kind == "bambu":
        from .bambu import BambuPrinter

        for key in ("host", "serial", "access_code"):
            if not cfg.get(key):
                raise ValueError(f"[printer] {key} is not set in config.toml")
        return BambuPrinter(name, cfg["host"], cfg["serial"], cfg["access_code"])
    raise ValueError(f"Unknown printer type: {kind!r}")
