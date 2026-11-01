import pytest
from fakes import FakeConnector

from app.core.config import settings
from app.services.snapshot import collect_snapshot


@pytest.fixture(autouse=True)
def cfg(monkeypatch):
    monkeypatch.setattr(settings, "parallel_connections", False)  # everything on the main connection
    monkeypatch.setattr(settings, "ccq_normal_percent", 70.0)
    monkeypatch.setattr(settings, "ccq_serious_percent", 50.0)
    monkeypatch.setattr(settings, "ccq_critical_percent", 35.0)
    monkeypatch.setattr(settings, "signal_normal_dbm", -60.0)
    monkeypatch.setattr(settings, "signal_warning_dbm", -70.0)
    monkeypatch.setattr(settings, "signal_serious_dbm", -80.0)
    monkeypatch.setattr(settings, "ap_expected_addresses", ["192.168.0.2/24", "192.168.1.2/24"])


class Conn(FakeConnector):
    def __init__(self, ip, tid):
        super().__init__(ip, tid)
        self.api.tables[("ip", "address")] = [
            {"address": "192.168.0.2/24", "interface": "ether1"},
            {"address": "10.0.0.1/24", "interface": "wlan1"},
        ]
        registration = self.api.tables[("interface", "wireless", "registration-table")][0]
        registration.update(
            {
                "tx-ccq": 63,
                "rx-ccq": 26,
                "tx-signal-strength-ch1": -50,
                "signal-strength-ch1": -85,
            }
        )


def test_ether1_reports_which_expected_addresses_are_set():
    report = collect_snapshot("10.229.2.50", "10047", connector_cls=Conn)
    ether1 = report["sections"]["ether1"]["data"]
    assert ether1["addresses"] == ["192.168.0.2/24"]
    assert ether1["expected_addresses"] == [
        {"address": "192.168.0.2/24", "configured": True},
        {"address": "192.168.1.2/24", "configured": False},
    ]


def test_each_ccq_direction_and_chain_gets_its_own_level():
    wireless = collect_snapshot("10.229.2.50", "10047", connector_cls=Conn)["sections"]["wireless"]["data"]
    analysis = wireless["analysis"]
    assert analysis["ccq_tx"] == "warning"
    assert analysis["ccq_rx"] == "critical"
    assert analysis["ccq"] == "critical"  # a bad direction is not hidden by a good one
    assert analysis["overall"] == "critical"
    assert analysis["chains"] == [
        {"chain": 0, "level": "normal"},
        {"chain": 1, "level": "critical"},
    ]
    assert wireless["registration"]["chains"][0] == {"chain": 0, "tx_dbm": -52.0, "rx_dbm": -50.0}