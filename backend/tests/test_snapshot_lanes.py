import pytest
from fakes import FakeConnector, NoExtraConnector

from app.core.config import settings
from app.services.live import collect_live
from app.services.snapshot import SECTIONS, collect_snapshot


@pytest.fixture(autouse=True)
def cfg(monkeypatch):
    monkeypatch.setattr(settings, "parallel_connections", True)
    monkeypatch.setattr(settings, "ping_targets", ["8.8.8.8"])
    monkeypatch.setattr(settings, "queue_very_low_limit_bps", 10_000)


def check_report(report):
    assert list(report["sections"]) == list(SECTIONS)
    sections = report["sections"]

    assert sections["identity"]["data"]["identity"] == "R-Test"
    assert sections["resource"]["data"]["ram_used_percent"] == 40.0
    assert sections["temperature"]["ok"] is False

    wireless = sections["wireless"]["data"]
    assert wireless["registration"]["radio_name"] == "HKB-1739"
    assert wireless["registration"]["chains"] == [
        {"chain": 0, "tx_dbm": -52.0, "rx_dbm": -50.0},
        {"chain": 1, "tx_dbm": -50.0, "rx_dbm": -44.0},
    ]

    ether1 = sections["ether1"]["data"]
    assert ether1["link_rate"] == "100Mbps"
    assert ether1["link_downs"] == 2

    devices = sections["devices"]["data"]
    assert devices["count"] == 1
    assert devices["devices"][0]["hostname"] == "phone"
    assert devices["devices"][0]["queue_scope"] == "own"
    assert devices["total_traffic"]["upload_bps"] == 1000

    assert sections["queues"]["data"]["matched_count"] == 1

    pppoe = sections["pppoe"]["data"]
    assert pppoe["username"] == "user1"
    assert pppoe["matches_panel_ip"] is True
    assert report["timings_ms"]["total"] >= 0


def test_snapshot_with_parallel_lanes():
    connector = {}

    class Tracking(FakeConnector):
        def __init__(self, ip, tid):
            super().__init__(ip, tid)
            connector["conn"] = self

    check_report(collect_snapshot("10.229.2.50", "10047", connector_cls=Tracking))
    assert len(connector["conn"].extras) == 2
    assert all(extra.closed for extra in connector["conn"].extras)


def test_snapshot_falls_back_to_the_main_connection():
    check_report(collect_snapshot("10.229.2.50", "10047", connector_cls=NoExtraConnector))


def test_snapshot_without_parallel_connections(monkeypatch):
    monkeypatch.setattr(settings, "parallel_connections", False)
    check_report(collect_snapshot("10.229.2.50", "10047", connector_cls=FakeConnector))


def test_live_measurements():
    live = collect_live("10.229.2.50", "10047", connector_cls=FakeConnector)
    assert live["ping"]["ok"] is True
    target = live["ping"]["data"]["targets"][0]
    assert target["reachable"] is True
    assert live["ping"]["data"]["gateway"] is None
    assert "mac_ping" not in live
    assert live["ap_probe"]["ok"] is True
    assert live["diagnostics"]["findings"] == []


def test_live_falls_back_when_extra_connection_is_refused():
    live = collect_live("10.229.2.50", "10047", connector_cls=NoExtraConnector)
    assert live["ap_probe"]["ok"] is True
    assert live["ping"]["ok"] is True