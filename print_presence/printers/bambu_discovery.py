"""Find Bambu Lab printers on the local network.

Printers announce themselves every few seconds with SSDP-like NOTIFY packets on
UDP 2021 (broadcast) and 239.255.255.250:1990 (multicast):

    NOTIFY * HTTP/1.1
    Location: 192.168.1.64
    NT: urn:bambulab-com:device:3dprinter:1
    USN: <serial>
    DevModel.bambu.com: C12
    DevName.bambu.com: Home Printer

The access code is never announced; the user has to type it.
"""

from __future__ import annotations

import logging
import socket
import struct
import time
from dataclasses import dataclass

log = logging.getLogger(__name__)

PORTS = (2021, 1990)
MCAST_GROUP = "239.255.255.250"
SEARCH_TARGET = "urn:bambulab-com:device:3dprinter:1"

# DevModel.bambu.com codes reported by the firmware.
MODEL_CODES = {
    "3DPrinter-X1-Carbon": "X1C",
    "3DPrinter-X1": "X1",
    "BL-P001": "X1C",
    "BL-P002": "X1",
    "C11": "P1P",
    "C12": "P1S",
    "C13": "X1E",
    "N1": "A1 mini",
    "N2S": "A1",
    "O1D": "H2D",
    "O1S": "H2S",
    "N7": "P2S",
}

# First characters of the serial number, used when the model code is unknown.
SERIAL_PREFIXES = {
    "00M": "X1C",
    "00W": "X1",
    "03W": "X1E",
    "01S": "P1P",
    "01P": "P1S",
    "030": "A1 mini",
    "039": "A1",
    "094": "H2D",
    "239": "H2D Pro",
    "093": "H2S",
}


def model_name(model_code: str | None = None, serial: str | None = None) -> str | None:
    if model_code and model_code in MODEL_CODES:
        return MODEL_CODES[model_code]
    if serial:
        for prefix, name in SERIAL_PREFIXES.items():
            if serial.upper().startswith(prefix):
                return name
    return None


def display_name(model_code: str | None = None, serial: str | None = None) -> str:
    model = model_name(model_code, serial)
    return f"Bambu Lab {model}" if model else "Bambu Lab"


@dataclass(frozen=True)
class FoundPrinter:
    host: str
    serial: str
    model_code: str
    name: str  # name the user gave the printer in Bambu Studio / Handy

    @property
    def model(self) -> str:
        return model_name(self.model_code, self.serial) or self.model_code or "Bambu Lab"

    @property
    def title(self) -> str:
        return f"{self.name} · {self.model} · {self.host}" if self.name else f"{self.model} · {self.host}"


def parse_announcement(data: bytes, sender_ip: str) -> FoundPrinter | None:
    try:
        text = data.decode("utf-8", errors="replace")
    except Exception:
        return None
    headers: dict[str, str] = {}
    for line in text.splitlines()[1:]:
        key, sep, value = line.partition(":")
        if sep:
            headers[key.strip().lower()] = value.strip()
    if "bambulab" not in headers.get("nt", "") + headers.get("st", ""):
        return None
    serial = headers.get("usn", "")
    if not serial:
        return None
    return FoundPrinter(
        host=headers.get("location") or sender_ip,
        serial=serial,
        model_code=headers.get("devmodel.bambu.com", ""),
        name=headers.get("devname.bambu.com", ""),
    )


def _open_socket(port: int) -> socket.socket | None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    try:
        sock.bind(("", port))
    except OSError as e:
        log.warning("Порт %d занят (%s) — возможно, открыт Bambu Studio", port, e)
        sock.close()
        return None
    try:
        mreq = struct.pack("4s4s", socket.inet_aton(MCAST_GROUP), socket.inet_aton("0.0.0.0"))
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    except OSError:
        pass  # multicast is optional, broadcast on 2021 is enough
    sock.setblocking(False)
    return sock


def _send_search(sock: socket.socket) -> None:
    for addr in (("255.255.255.255", 2021), (MCAST_GROUP, 1990)):
        msg = (
            "M-SEARCH * HTTP/1.1\r\n"
            f"HOST: {addr[0]}:{addr[1]}\r\n"
            'MAN: "ssdp:discover"\r\n'
            "MX: 1\r\n"
            f"ST: {SEARCH_TARGET}\r\n\r\n"
        )
        try:
            sock.sendto(msg.encode(), addr)
        except OSError:
            pass


def discover(timeout: float = 8.0) -> list[FoundPrinter]:
    """Listen for printer announcements for `timeout` seconds."""
    import select

    socks = [s for s in (_open_socket(p) for p in PORTS) if s]
    if not socks:
        return []
    found: dict[str, FoundPrinter] = {}
    try:
        _send_search(socks[0])
        deadline = time.monotonic() + timeout
        while (left := deadline - time.monotonic()) > 0:
            ready, _, _ = select.select(socks, [], [], min(left, 0.5))
            for s in ready:
                try:
                    data, (ip, _) = s.recvfrom(4096)
                except OSError:
                    continue
                printer = parse_announcement(data, ip)
                if printer and printer.serial not in found:
                    log.info("Найден принтер: %s", printer.title)
                    found[printer.serial] = printer
    finally:
        for s in socks:
            s.close()
    return list(found.values())
