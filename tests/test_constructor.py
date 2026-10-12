import dataclasses
import threading
import time

from pypresence.types import ActivityType, StatusDisplayType

from print_presence import runner
from print_presence.presence import (DEFAULT_TEMPLATES, REPO_URL, PrintClock, build_activity, custom_options,
                                     discord_payload, fit_bytes, render_template, valid_url)
from print_presence.status import PrinterStatus, State

PRINTING = PrinterStatus(state=State.PRINTING, job_name="Benchy.3mf", progress=42, layer=87, total_layers=240,
                         remaining_min=83, nozzle_temp=219.6, bed_temp=65, filament="PLA Basic",
                         filament_color="161616FF")


def custom(**kw):
    return dict(custom_options({}), enabled=True, **kw)


def test_groups_disappear_when_a_value_is_empty():
    values = {"status": "Idle", "job": "", "progress": "42%"}
    assert render_template("{status}[: {job}]", values) == "Idle"
    assert render_template("[{job}][ · {progress}]", values) == "42%"
    assert render_template("{status} · {job} · {progress}", values) == "Idle · 42%"
    assert render_template("Hi {typo}", values) == "Hi {typo}"  # unknown names stay visible


def test_default_templates_match_the_standard_status():
    standard = build_activity(PRINTING, "P1S", "en", now=0)
    templated = build_activity(PRINTING, "P1S", "en", now=0, custom=custom())
    for key in ("details", "state", "large_text", "small_text", "end", "buttons"):
        assert templated[key] == standard[key], key


def test_custom_lines_and_timer():
    a = build_activity(PRINTING, "P1S", "ru", now=0,
                       custom=custom(details="🖨 {job}", state="⏳ {remaining} · {progress}", timer=False))
    assert a["details"] == "🖨 Benchy.3mf"
    assert a["state"] == "⏳ 1 ч 23 мин · 42%"
    assert "end" not in a


def test_progress_values_are_empty_when_not_printing():
    idle = PrinterStatus(state=State.IDLE, nozzle_temp=25)
    a = build_activity(idle, "P1S", "en", custom=custom())
    assert a["details"] == "Idle"
    assert "state" not in a
    # an empty line falls back to the status so Discord always has something to show
    assert build_activity(idle, "P1S", "en", custom=custom(details="[{job}]"))["details"] == "Idle"


def test_hide_job_applies_to_templates():
    a = build_activity(PRINTING, "P1S", "en", hide_job=True, custom=custom(details="{status}[: {job}]"))
    assert a["details"] == "Printing"


def test_custom_options_fill_defaults():
    assert custom_options({}) == DEFAULT_TEMPLATES
    assert custom_options({"custom": {"enabled": True, "details": "x", "junk": 1}})["details"] == "x"
    assert "junk" not in custom_options({"custom": {"junk": 1}})


class FakePrinter:
    name = "P1S"

    def start(self):
        pass

    def stop(self):
        pass

    def status(self):
        return PRINTING


def test_runner_applies_changes_without_restart(monkeypatch):
    sent = []

    class FakeDiscord:
        connected = True

        def __init__(self, _cid):
            pass

        def set(self, activity):
            sent.append(activity)

        def close(self):
            pass

    monkeypatch.setattr(runner, "DiscordPresence", FakeDiscord)
    monkeypatch.setattr(runner, "create_printer", lambda _cfg: FakePrinter())
    monkeypatch.setattr(runner, "LIVE_GAP_S", 0)
    cfg = {"discord": {}, "printers": [{"host": "1", "serial": "S", "access_code": "x"}],
           "presence": {"language": "en"}}
    r = runner.Runner(cfg)
    r.start()
    deadline = time.time() + 6
    while not sent and time.time() < deadline:
        time.sleep(0.05)
    assert sent and sent[-1]["details"] == "Printing: Benchy.3mf"
    r.update_presence(dict(cfg, presence={"language": "en", "custom": custom(details="Hello {job}")}))
    deadline = time.time() + 2
    while sent[-1]["details"] != "Hello Benchy.3mf" and time.time() < deadline:
        time.sleep(0.05)
    r.stop()
    assert sent[-1]["details"] == "Hello Benchy.3mf"
    assert not any(t.name == "print-presence" and t.is_alive() for t in threading.enumerate())


def test_old_timer_switch_is_migrated():
    assert custom_options({"custom": {"timer": False}})["timer"] == "none"
    assert custom_options({"custom": {"timer": True}})["timer"] == "remaining"
    assert custom_options({"custom": {"party": "bogus", "activity_type": 1}})["party"] == "none"
    assert custom_options({"custom": {"activity_type": 1}})["activity_type"] == 0  # streaming isn't allowed


def test_own_text_per_state():
    c = custom(overrides={"finished": {"details": "Done: {job}", "state": "", "large_text": "", "small_text": ""}})
    finished = PrinterStatus(state=State.FINISHED, job_name="Benchy.3mf")
    assert build_activity(finished, "P1S", "en", custom=c)["details"] == "Done: Benchy.3mf"
    assert build_activity(PRINTING, "P1S", "en", custom=c)["details"] == "Printing: Benchy.3mf"


def test_hidden_fields():
    a = build_activity(PRINTING, "P1S", "en", custom=custom(hidden=["state", "large_text", "small_image"]))
    for key in ("state", "large_text", "small_image", "small_text"):
        assert key not in a
    b = build_activity(PRINTING, "P1S", "en", custom=custom(hidden=["small_text"]))
    assert b["small_image"] == "printing" and "small_text" not in b


def test_timer_party_type_and_member_list():
    a = build_activity(PRINTING, "P1S", "en", now=10_000, started=6_000,
                       custom=custom(timer="elapsed", party="layers", activity_type=3, status_display="details"))
    assert a["start"] == 6_000 and "end" not in a
    assert a["party_size"] == [87, 240] and a["party_id"]
    payload = discord_payload(a)
    assert payload["activity_type"] == ActivityType.WATCHING
    assert payload["status_display_type"] == StatusDisplayType.DETAILS
    b = build_activity(PRINTING, "P1S", "en", custom=custom(party="progress", timer="none"))
    assert b["party_size"] == [42, 100] and "end" not in b and "start" not in b
    assert "activity_type" not in build_activity(PRINTING, "P1S", "en", custom=custom())
    idle = build_activity(PrinterStatus(state=State.IDLE), "P1S", "en", custom=custom(party="layers"))
    assert "party_size" not in idle


def test_own_button():
    c = custom(button_on=True, button_label="Модель на MakerWorld и ещё текст", button_url="https://makerworld.com/x")
    a = build_activity(PRINTING, "P1S", "en", custom=c)
    assert [b["url"] for b in a["buttons"]] == ["https://makerworld.com/x", REPO_URL]
    assert len(a["buttons"][0]["label"].encode()) <= 32
    bad = build_activity(PRINTING, "P1S", "en", custom=dict(c, button_url="makerworld"))
    assert len(bad["buttons"]) == 1
    assert fit_bytes("Привет мир, как дела?") == "Привет мир, как де"  # exactly 32 bytes
    assert valid_url("https://a.b/c") and not valid_url("javascript:alert(1)")


def test_print_clock_estimates_start():
    clock = PrintClock()
    # 25% done, 60 minutes left -> started about 20 minutes ago
    start = clock.update(dataclasses.replace(PRINTING, progress=25, remaining_min=60), now=100_000)
    assert abs((100_000 - start) - 20 * 60) < 60
    assert clock.update(dataclasses.replace(PRINTING, progress=30), now=100_600) == start  # same job
    assert clock.update(PrinterStatus(state=State.OFFLINE)) is None and clock.start == start  # short drop
    assert clock.update(PrinterStatus(state=State.IDLE)) is None and clock.start is None
