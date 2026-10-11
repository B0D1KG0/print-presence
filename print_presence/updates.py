"""Checks GitHub for a newer release."""

from __future__ import annotations

import json
import re
import urllib.request

from . import __version__

LATEST_URL = "https://api.github.com/repos/B0D1KG0/print-presence/releases/latest"


def parse_version(text: str) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", text)[:3])


def check(current: str = __version__, timeout: float = 6.0) -> tuple[str, str] | None:
    """(version, release page URL) if GitHub has something newer; None otherwise or on any error."""
    try:
        req = urllib.request.Request(LATEST_URL, headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"print-presence/{current}",
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.load(resp)
        tag = str(data.get("tag_name", ""))
        if tag and parse_version(tag) > parse_version(current):
            return tag, str(data.get("html_url") or "https://github.com/B0D1KG0/print-presence/releases")
    except Exception:
        pass
    return None
