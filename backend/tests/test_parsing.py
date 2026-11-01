from app.services.parsing import (
    leading_number,
    parse_registration,
    pick_wireless_interface,
    to_bool,
)
from app.services.snapshot import parse_temperature


def test_leading_number_formats():
    assert leading_number(-62) == -62.0
    assert leading_number("-62") == -62.0
    assert leading_number("-62@HT20-5") == -62.0
    assert leading_number("-62dBm") == -62.0
    assert leading_number("87") == 87.0
    assert leading_number(None) is None
    assert leading_number("n/a") is None
    assert leading_number(True) is None


def test_to_bool():
    assert to_bool(True) is True
    assert to_bool("yes") is True
    assert to_bool("false") is False
    assert to_bool(None) is None
    assert to_bool("maybe") is None


def test_pick_wireless_interface_prefers_wlan1():
    rows = [{"name": "wlan2"}, {"name": "wlan1"}]
    assert pick_wireless_interface(rows)["name"] == "wlan1"


def test_pick_wireless_interface_falls_back_to_first():
    rows = [{"name": "wlan5"}, {"name": "wlan6"}]
    assert pick_wireless_interface(rows)["name"] == "wlan5"
    assert pick_wireless_interface([]) is None


def test_parse_registration_with_snr():
    row = {
        "interface": "wlan1",
        "mac-address": "AA:BB:CC:DD:EE:FF",
        "radio-name": "HKB-1554",
        "signal-strength": "-65@HT20-5",
        "signal-to-noise": 30,
        "tx-ccq": 88,
        "rx-ccq": 91,
    }
    reg = parse_registration(row)
    assert reg["signal_dbm"] == -65.0
    assert reg["noise_floor_dbm"] == -95.0
    assert reg["tx_ccq"] == 88.0
    assert reg["radio_name"] == "HKB-1554"


def test_parse_registration_missing_values():
    reg = parse_registration({"interface": "wlan1"})
    assert reg["signal_dbm"] is None
    assert reg["noise_floor_dbm"] is None
    assert reg["tx_ccq"] is None


def test_temperature_v6():
    assert parse_temperature([{"voltage": 24, "temperature": 45}]) == 45.0


def test_temperature_v7():
    rows = [{"name": "voltage", "value": "24"}, {"name": "temperature", "value": "47"}]
    assert parse_temperature(rows) == 47.0


def test_temperature_missing():
    assert parse_temperature([{"voltage": 24}]) is None