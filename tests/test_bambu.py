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


def test_client_id_falls_back_to_default(monkeypatch):
    from print_presence import presence
    monkeypatch.setattr(presence, "DEFAULT_CLIENT_ID", "111")
    assert presence.client_id_from({"discord": {"client_id": " "}}) == "111"
    assert presence.client_id_from({}) == "111"
    # config.toml without the switch: an own ID wins
    assert presence.client_id_from({"discord": {"client_id": "222"}}) == "222"
    # GUI switch
    assert presence.client_id_from({"discord": {"use_default": True, "client_id": "222"}}) == "111"
    assert presence.client_id_from({"discord": {"use_default": False, "client_id": "222"}}) == "222"
    assert presence.client_id_from({"discord": {"use_default": False, "client_id": ""}}) == ""


AMS_REPORT = {
    "gcode_state": "RUNNING",
    "ams": {
        "tray_now": "1",
        "ams": [{"id": "0", "tray": [
            {"id": "0", "tray_type": "PETG", "tray_sub_brands": "PETG HF", "tray_color": "FFFFFFFF"},
            {"id": "1", "tray_type": "PLA", "tray_sub_brands": "PLA Basic", "tray_color": "161616FF"},
        ]}],
    },
    "vt_tray": {"id": "254", "tray_type": "TPU", "tray_color": "FF0000FF"},
}


def test_filament_from_ams():
    s = parse_report(AMS_REPORT)
    assert (s.filament, s.filament_color) == ("PLA Basic", "161616FF")


def test_filament_external_spool_and_no_ams():
    ext = dict(AMS_REPORT, ams={**AMS_REPORT["ams"], "tray_now": "254"})
    assert parse_report(ext).filament == "TPU"
    no_ams = {"gcode_state": "RUNNING", "ams": {"tray_now": "255", "ams": []},
              "vt_tray": {"tray_type": "PLA", "tray_color": "0000FFFF"}}
    assert parse_report(no_ams).filament == "PLA"
    unloaded = dict(AMS_REPORT, ams={**AMS_REPORT["ams"], "tray_now": "255"})
    assert parse_report(unloaded).filament is None


def test_deep_merge_keeps_nested_fields():
    from print_presence.printers.bambu import deep_merge
    data = {"ams": {"tray_now": "0", "ams": [1]}, "mc_percent": 1}
    deep_merge(data, {"ams": {"tray_now": "2"}, "mc_percent": 5})
    assert data == {"ams": {"tray_now": "2", "ams": [1]}, "mc_percent": 5}


def test_color_names():
    from print_presence.filament import color_name, filament_label
    assert color_name("161616FF", "ru") == "Чёрный"
    assert color_name("FFFFFFFF", "en") == "White"
    assert color_name("D21E28FF", "uk") == "Червоний"
    assert color_name("FFFFFF00", "en") == "Clear"
    assert color_name("zz", "en") is None
    assert filament_label("PLA Basic", "161616FF", "ru") == "PLA Basic · Чёрный"


def test_activity_filament_button_and_privacy():
    s = parse_report({**REPORT, **AMS_REPORT})
    a = build_activity(s, "Bambu Lab P1S", "ru")
    assert a["large_text"] == "Bambu Lab P1S · PLA Basic · Чёрный"
    assert a["buttons"] == [{"label": "Get Print Presence", "url": "https://github.com/B0D1KG0/print-presence"}]
    hidden = build_activity(s, "Bambu Lab P1S", "en", hide_job=True, button=False)
    assert hidden["details"] == "Printing"
    assert "buttons" not in hidden
    done = build_activity(PrinterStatus(state=State.FINISHED, job_name="secret_part"), "P1S", "uk", hide_job=True)
    assert done["details"] == "Друк завершено" and "state" not in done


def test_name_is_not_sent_to_discord():
    from print_presence.presence import discord_payload
    a = build_activity(parse_report(REPORT), "My printer", "en")
    payload = discord_payload(a)
    assert "name" not in payload
    assert payload["details"] == a["details"]


def test_button_label_fits_discord_byte_limit():
    from print_presence.presence import BUTTON_LABEL
    for lang in ("en", "ru", "uk"):
        a = build_activity(parse_report(REPORT), "P1S", lang)
        for b in a["buttons"]:
            assert 1 <= len(b["label"].encode("utf-8")) <= 32
            assert len(b["url"]) <= 512
