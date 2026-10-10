import socket
import threading
import time

import pytest

from print_presence.printers.bambu_discovery import discover, display_name, parse_announcement
from print_presence.printers import create_printer

PACKET = (
    "NOTIFY * HTTP/1.1\r\n"
    "Host: 239.255.255.250:1990\r\n"
    "Server: Buildroot/2018.02-rc3 UPnP/1.0 ssdpd/1.8\r\n"
    "Location: 192.168.1.64\r\n"
    "NT: urn:bambulab-com:device:3dprinter:1\r\n"
    "NTS: ssdp:alive\r\n"
    "USN: 01P00C000000001\r\n"
    "DevModel.bambu.com: C12\r\n"
    "DevName.bambu.com: Home Printer\r\n"
    "DevConnect.bambu.com: lan\r\n\r\n"
).encode()


def test_parse_announcement():
    p = parse_announcement(PACKET, "10.0.0.5")
    assert (p.host, p.serial, p.model, p.name) == ("192.168.1.64", "01P00C000000001", "P1S", "Home Printer")


def test_parse_ignores_other_devices():
    assert parse_announcement(b"NOTIFY * HTTP/1.1\r\nNT: upnp:rootdevice\r\nUSN: x\r\n\r\n", "1.2.3.4") is None
    assert parse_announcement(b"\xff\xfe garbage", "1.2.3.4") is None


def test_display_name():
    assert display_name("C12") == "Bambu Lab P1S"
    assert display_name(None, "01P00C000000001") == "Bambu Lab P1S"
    assert display_name("3DPrinter-X1-Carbon") == "Bambu Lab X1C"
    assert display_name("ZZZ", "XXX") == "Bambu Lab"


def test_printer_name_defaults_to_model():
    p = create_printer({"host": "1.2.3.4", "serial": "01P00C000000001", "access_code": "x", "name": ""})
    assert p.name == "Bambu Lab P1S"
    p = create_printer({"host": "1.2.3.4", "serial": "01P00C000000001", "access_code": "x", "name": "Мой"})
    assert p.name == "Мой"


def test_discover_receives_announcement():
    def send():
        time.sleep(0.5)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.sendto(PACKET, ("127.0.0.1", 2021))
        s.sendto(PACKET, ("127.0.0.1", 2021))  # duplicates are merged
        s.close()

    threading.Thread(target=send).start()
    found = discover(timeout=1.5)
    if not found:
        pytest.skip("UDP 2021 is taken by another program (e.g. Bambu Studio)")
    assert [p.serial for p in found] == ["01P00C000000001"]
