from print_presence.presence import build_activity
from print_presence.printers.bambu import parse_report
from print_presence.status import PrinterStatus, State

REPORT = {
    "gcode_state": "RUNNING",
    "subtask_name": "benchy.gcode.3mf",
    "mc_percent": 36,
    "mc_remaining_time": 72,
    "layer_num": 87,
    "total_layer_num": 240,
    "nozzle_temper": 219.8,
    "bed_temper": 65.1,
    "spd_lvl": 2,
}


def test_parse_running():
    s = parse_report(REPORT)
    assert s.state == State.PRINTING
    assert s.job_name == "benchy"
    assert (s.layer, s.total_layers, s.progress, s.remaining_min) == (87, 240, 36, 72)
    assert s.speed_profile == "standard"


def test_parse_unknown_and_garbage():
    s = parse_report({"gcode_state": "WEIRD", "mc_percent": "x"})
    assert s.state == State.IDLE
    assert s.progress is None


def test_activity_printing():
    a = build_activity(parse_report(REPORT), "Bambu Lab P1S", "ru", now=1_000_000)
    assert a["name"] == "Bambu Lab P1S"
    assert a["details"] == "Печатает: benchy"
    assert a["state"] == "Слой 87/240 · 36%"
    assert a["small_image"] == "printing"
    assert a["small_text"] == "Сопло 220°C · Стол 65°C"
    assert a["end"] == (1_000_000 + 72 * 60) // 60 * 60


def test_activity_finished_and_offline():
    a = build_activity(PrinterStatus(state=State.FINISHED, job_name="benchy"), "P1S", "en")
    assert a["details"] == "Print finished"
    assert a["state"] == "benchy"
    assert "end" not in a
    assert build_activity(PrinterStatus(), "P1S") is None


def test_calibration_job_is_renamed():
    s = parse_report({"gcode_state": "FINISH", "subtask_name": "pa_line_calib_mode"})
    assert s.calibration
    a = build_activity(s, "P1S", "ru")
    assert a["state"] == "Калибровка"
