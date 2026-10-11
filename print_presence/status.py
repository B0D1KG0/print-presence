"""Printer-agnostic status model. Every printer backend converts its data into this."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class State(str, Enum):
    OFFLINE = "offline"
    IDLE = "idle"
    PREPARING = "preparing"
    PRINTING = "printing"
    PAUSED = "paused"
    FINISHED = "finished"
    FAILED = "failed"


@dataclass(frozen=True)
class PrinterStatus:
    state: State = State.OFFLINE
    job_name: str | None = None
    progress: int | None = None  # 0..100
    layer: int | None = None
    total_layers: int | None = None
    remaining_min: int | None = None
    nozzle_temp: float | None = None
    bed_temp: float | None = None
    speed_profile: str | None = None  # "silent", "standard", "sport", "ludicrous"
    calibration: bool = False  # the printer runs its own calibration, not a user model
    filament: str | None = None  # material of the active spool, e.g. "PLA Basic"
    filament_color: str | None = None  # "RRGGBB" or "RRGGBBAA"
