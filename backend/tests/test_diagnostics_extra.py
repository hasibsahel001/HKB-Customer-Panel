import pytest

from app.core.config import settings
from app.services.diagnostics import diagnose, diagnose_live


@pytest.fixture(autouse=True)
def thresholds(monkeypatch):
    monkeypatch.setattr(settings, "chain_imbalance_db", 8.0)
    monkeypatch.setattr(settings, "link_downs_warning", 5)
    monkeypatch.setattr(settings, "ping_loss_warning_percent", 2.0)
    monkeypatch.setattr(settings, "ping_loss_serious_percent", 10.0)
    monkeypatch.setattr(settings, "signal_normal_dbm", -60.0)
    monkeypatch.setattr(settings, "signal_warning_dbm", -70.0)
    monkeypatch.setattr(settings, "signal_serious_dbm", -80.0)
    monkeypatch.setattr(settings, "ccq_normal_percent", 80.0)
    monkeypatch.setattr(settings, "ccq_serious_percent", 60.0)


def ok(data):
    return {"ok": True, "data": data, "error": None}


def snap(**sections):
    return {"sections": sections}


def codes(result):
    return {f["code"]: f for f in result["findings"]}


def is_persian(text):
    return any("\u0600" <= ch <= "\u06ff" for ch in text)


def wireless(chains=None, signal="normal", ccq="normal", uptime="1w", tx=90, rx=95):
    return {
        "interface": "wlan1",
        "running": True,
        "disabled": False,
        "registration_count": 1,
        "registration": {
            "signal_dbm": -55,
            "snr_db": 40,
            "noise_floor_dbm": -95,
            "chains": chains or [],
            "tx_ccq": tx,
            "rx_ccq": rx,
            "uptime": uptime,
        },
        "ccq_used": tx,
        "ccq_source": "tx",
        "analysis": {"signal": signal, "ccq": ccq, "overall": signal if signal != "normal" else ccq},
    }


def test_findings_are_persian():
    result = diagnose(snap(wireless=ok(wireless(signal="serious", ccq="warning"))))
    finding = codes(result)["wireless_link_quality_low"]
    assert is_persian(finding["title"])
    assert is_persian(finding["suggested_action"])
    assert all(is_persian(cause) for cause in finding["probable_causes"])
    assert "Shift" in finding["suggested_action"]



def test_asymmetric_ccq_adds_a_specific_cause():
    result = diagnose(snap(wireless=ok(wireless(ccq="warning", tx=50, rx=99))))
    causes = codes(result)["wireless_ccq_low_with_good_signal"]["probable_causes"]
    assert "یک‌طرفه" in causes[0]


def test_recent_wireless_drop_needs_a_long_running_device():
    wl = ok(wireless(uptime="2m"))
    res = ok({"uptime": "5w1d"})
    assert "wireless_link_recent_drop" in codes(diagnose(snap(wireless=wl, resource=res)))
    young = ok({"uptime": "3m"})
    assert "wireless_link_recent_drop" not in codes(diagnose(snap(wireless=wl, resource=young)))


@pytest.mark.parametrize(
    "ether1, expected",
    [
        ({"running": True, "link_rate": "10Mbps", "full_duplex": True}, True),
        ({"running": True, "link_rate": "100Mbps", "full_duplex": False}, True),
        ({"running": True, "link_rate": "100Mbps", "full_duplex": True}, False),
        ({"running": True, "link_rate": "1Gbps", "full_duplex": True}, False),
        ({"running": True}, False),
    ],
)
def test_lan_link_slow(ether1, expected):
    assert ("lan_link_slow" in codes(diagnose(snap(ether1=ok(ether1))))) is expected


def test_lan_link_flapping():
    result = diagnose(snap(ether1=ok({"running": True, "link_rate": "100Mbps", "full_duplex": True, "link_downs": 7})))
    assert "lan_link_flapping" in codes(result)
    few = diagnose(snap(ether1=ok({"running": True, "link_rate": "100Mbps", "full_duplex": True, "link_downs": 2})))
    assert "lan_link_flapping" not in codes(few)


def test_pppoe_recent_reconnect():
    pppoe = {"running": True, "status": "connected", "matches_panel_ip": True, "uptime": "2m"}
    result = diagnose(snap(pppoe=ok(pppoe), wireless=ok(wireless(uptime="2d"))))
    assert "pppoe_recent_reconnect" in codes(result)
    stable = diagnose(snap(pppoe=ok({**pppoe, "uptime": "3h"}), wireless=ok(wireless(uptime="2d"))))
    assert "pppoe_recent_reconnect" not in codes(stable)


def test_live_findings_without_ping_data_are_empty():
    assert diagnose_live(None, None)["findings"] == []
    assert diagnose_live(None, None)["overall"] == "normal"


def test_live_internet_ping_findings():
    ping = {
        "layers": {"internet_reachable": False},
        "gateway": None,
        "targets": [{"host": "8.8.8.8", "reachable": False, "status": "critical", "summary": None}],
    }
    result = diagnose_live(ping, None)
    assert codes(result)["internet_unreachable"]["severity"] == "serious"



def test_a_single_link_down_is_reported(monkeypatch):
    monkeypatch.setattr(settings, "link_downs_warning", 1)
    result = diagnose(snap(ether1=ok({"running": True, "link_rate": "100Mbps", "full_duplex": True, "link_downs": 1})))
    assert "lan_link_flapping" in codes(result)
    none = diagnose(snap(ether1=ok({"running": True, "link_rate": "100Mbps", "full_duplex": True, "link_downs": 0})))
    assert "lan_link_flapping" not in codes(none)