from print_presence import settings
from print_presence.runner import pick_featured, validate
from print_presence.status import PrinterStatus, State

import pytest


def st(state):
    return PrinterStatus(state=state)


def test_pick_featured_prefers_busy_and_is_sticky():
    assert pick_featured([st(State.IDLE), st(State.PRINTING)]) == 1
    assert pick_featured([st(State.OFFLINE), st(State.IDLE)]) == 1
    both = [st(State.PRINTING), st(State.PRINTING)]
    assert pick_featured(both, current=1) == 1  # don't flip between two busy printers
    assert pick_featured([st(State.PRINTING), st(State.FINISHED)], current=1) == 0


def test_migrates_single_printer(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"printer": {"host": "1.2.3.4", "serial": "S", "access_code": "x"}}', encoding="utf-8")
    cfg = settings.load(path)
    assert "printer" not in cfg
    assert cfg["printers"][0]["host"] == "1.2.3.4"
    assert cfg["printers"][0]["type"] == "bambu"


def test_validate_needs_a_printer():
    with pytest.raises(ValueError):
        validate({"discord": {}, "printers": []})
    validate({"discord": {}, "printers": [{"host": "1.2.3.4", "serial": "S", "access_code": "x"}]})
    # old single-printer config.toml still works
    validate({"discord": {}, "printer": {"host": "1.2.3.4", "serial": "S", "access_code": "x"}})


def test_status_language_follows_interface_when_auto():
    from print_presence.runner import status_language
    assert status_language("auto", "uk") == "uk"
    assert status_language("en", "uk") == "en"
    assert status_language(None, "ru") == "ru"


def test_portable_mode_keeps_data_next_to_exe(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    exe_dir = tmp_path / "PrintPresence"
    exe_dir.mkdir()
    assert not settings.is_portable(exe_dir)
    assert settings.data_dir(exe_dir) == tmp_path / "appdata" / "PrintPresence"
    (exe_dir / settings.PORTABLE_MARKER).write_text("portable", encoding="utf-8")
    assert settings.is_portable(exe_dir)
    assert settings.data_dir(exe_dir) == exe_dir / "data"


def test_running_from_source_is_never_portable():
    assert settings.app_dir() is None
    assert not settings.is_portable()
