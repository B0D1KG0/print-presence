"""Bambu Lab printers (P1S, P1P, X1C, A1, ...) over local MQTT.

The printer runs an MQTT broker on port 8883 (TLS, self-signed certificate).
Login is "bblp", password is the LAN Access Code from the printer screen.
Reports arrive on device/<serial>/report. P1/A1 series send only the fields that
changed, so we keep a merged copy of everything received so far.
"""

from __future__ import annotations

import json
import logging
import ssl
import threading
import time
from pathlib import PurePosixPath
from typing import Any

import paho.mqtt.client as mqtt

from ..status import PrinterStatus, State
from .base import Printer

log = logging.getLogger(__name__)

MQTT_PORT = 8883
MQTT_USER = "bblp"
# P1/A1 boards are weak; Bambu recommends not requesting a full push too often.
PUSHALL_INTERVAL_S = 5 * 60

GCODE_STATES = {
    "IDLE": State.IDLE,
    "INIT": State.IDLE,
    "SLICING": State.PREPARING,
    "PREPARE": State.PREPARING,
    "RUNNING": State.PRINTING,
    "PAUSE": State.PAUSED,
    "FINISH": State.FINISHED,
    "FAILED": State.FAILED,
}

SPEED_LEVELS = {1: "silent", 2: "standard", 3: "sport", 4: "ludicrous"}


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _job_name(data: dict[str, Any]) -> str | None:
    name = data.get("subtask_name") or data.get("gcode_file")
    if not name:
        return None
    name = PurePosixPath(str(name)).name
    for ext in (".gcode.3mf", ".3mf", ".gcode"):
        if name.lower().endswith(ext):
            return name[: -len(ext)]
    return name


def parse_report(data: dict[str, Any]) -> PrinterStatus:
    """Convert the merged "print" section of a Bambu report into PrinterStatus."""
    state = GCODE_STATES.get(str(data.get("gcode_state", "")).upper(), State.IDLE)
    return PrinterStatus(
        state=state,
        job_name=_job_name(data),
        progress=_int(data.get("mc_percent")),
        layer=_int(data.get("layer_num")),
        total_layers=_int(data.get("total_layer_num")),
        remaining_min=_int(data.get("mc_remaining_time")),
        nozzle_temp=_float(data.get("nozzle_temper")),
        bed_temp=_float(data.get("bed_temper")),
        speed_profile=SPEED_LEVELS.get(_int(data.get("spd_lvl")) or 0),
    )


class BambuPrinter(Printer):
    def __init__(self, name: str, host: str, serial: str, access_code: str) -> None:
        super().__init__(name)
        self.host = host
        self.serial = serial
        self._lock = threading.Lock()
        self._data: dict[str, Any] = {}
        self._connected = False
        self._last_pushall = 0.0
        self._stopping = False

        self._client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"print-presence-{int(time.time())}",
        )
        self._client.username_pw_set(MQTT_USER, access_code)
        # The printer uses a self-signed certificate, so it can't be verified
        # against public CAs. Traffic is still encrypted.
        self._client.tls_set(cert_reqs=ssl.CERT_NONE)
        self._client.tls_insecure_set(True)
        self._client.reconnect_delay_set(min_delay=2, max_delay=60)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

    # Printer API -----------------------------------------------------------

    def start(self) -> None:
        log.info("Connecting to %s (%s)...", self.name, self.host)
        self._client.connect_async(self.host, MQTT_PORT, keepalive=60)
        self._client.loop_start()

    def stop(self) -> None:
        self._stopping = True
        self._client.disconnect()
        self._client.loop_stop()

    def status(self) -> PrinterStatus:
        with self._lock:
            if not self._connected or not self._data:
                return PrinterStatus(state=State.OFFLINE)
            status = parse_report(self._data)
        if time.monotonic() - self._last_pushall > PUSHALL_INTERVAL_S:
            self._request_pushall()
        return status

    # MQTT callbacks --------------------------------------------------------

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        if reason_code.is_failure:
            log.error(
                "Printer refused connection: %s. Check the IP and Access Code; "
                "if they are correct, enable LAN Only + Developer Mode on the printer.",
                reason_code,
            )
            return
        log.info("Connected to %s", self.name)
        client.subscribe(f"device/{self.serial}/report")
        with self._lock:
            self._connected = True
        self._request_pushall()

    def _on_disconnect(self, client, userdata, flags, reason_code, properties) -> None:
        with self._lock:
            self._connected = False
            self._data = {}
        if not self._stopping:
            log.warning("Disconnected from %s (%s), reconnecting...", self.name, reason_code)

    def _on_message(self, client, userdata, msg) -> None:
        try:
            payload = json.loads(msg.payload)
        except (ValueError, UnicodeDecodeError):
            return
        section = payload.get("print")
        if not isinstance(section, dict):
            return
        with self._lock:
            self._data.update(section)

    def _request_pushall(self) -> None:
        self._last_pushall = time.monotonic()
        request = {"pushing": {"sequence_id": "0", "command": "pushall", "version": 1, "push_target": 1}}
        self._client.publish(f"device/{self.serial}/request", json.dumps(request))
