import io
import json

from print_presence import updates, winstartup


def test_parse_version():
    assert updates.parse_version("v0.10.2") == (0, 10, 2)
    assert updates.parse_version("0.6.0") > updates.parse_version("v0.5.9")


def test_check_newer_and_older(monkeypatch):
    def fake(tag):
        body = json.dumps({"tag_name": tag, "html_url": "https://example.com/r"}).encode()
        return lambda req, timeout: io.BytesIO(body)

    monkeypatch.setattr(updates.urllib.request, "urlopen", fake("v0.7.0"))
    assert updates.check("0.6.0") == ("v0.7.0", "https://example.com/r")
    monkeypatch.setattr(updates.urllib.request, "urlopen", fake("v0.6.0"))
    assert updates.check("0.6.0") is None


def test_check_never_raises(monkeypatch):
    def boom(*a, **k):
        raise OSError("offline")

    monkeypatch.setattr(updates.urllib.request, "urlopen", boom)
    assert updates.check("0.6.0") is None


def test_winstartup_is_noop_off_windows():
    if not winstartup.supported():
        assert winstartup.is_enabled() is False
        winstartup.set_enabled(True)  # must not fail
