import threading
import time

from print_presence import runner
from print_presence.presence import DEFAULT_TEMPLATES, build_activity, custom_options, render_template
from print_presence.status import PrinterStatus, State

PRINTING = PrinterStatus(state=State.PRINTING, job_name="Benchy.3mf", progress=42, layer=87, total_layers=240,
                         remaining_min=83, nozzle_temp=219.6, bed_temp=65, filament="PLA Basic",
                         filament_color="161616FF")


def custom(**kw):
    return dict(DEFAULT_TEMPLATES, enabled=True, **kw)


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
