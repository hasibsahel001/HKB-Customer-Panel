from app.services.parsing import parse_registration


def test_chains_are_parsed_like_winbox():
    row = {
        "interface": "wlan1",
        "signal-strength": "-50@HT20",
        "tx-signal-strength-ch0": "-52",
        "signal-strength-ch0": "-50",
        "tx-signal-strength-ch1": -50,
        "signal-strength-ch1": -44,
    }
    reg = parse_registration(row)
    assert reg["chains"] == [
        {"chain": 0, "tx_dbm": -52.0, "rx_dbm": -50.0},
        {"chain": 1, "tx_dbm": -50.0, "rx_dbm": -44.0},
    ]


def test_chains_empty_when_not_reported():
    assert parse_registration({"interface": "wlan1"})["chains"] == []


def test_chain_with_only_one_direction():
    reg = parse_registration({"signal-strength-ch0": -60})
    assert reg["chains"] == [{"chain": 0, "tx_dbm": None, "rx_dbm": -60.0}]