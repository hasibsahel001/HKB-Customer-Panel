from fakes import FakeApi, FakeConnector, make_commands, make_tables

from app.core.config import settings
from app.services.live import collect_live


def respond(words):
    if "=address=192.168.0.1" in words:
        return [{"host": "192.168.0.1", "sent": 2, "received": 2, "packet-loss": 0, "avg-rtt": "3ms", "time": "3ms"}]
    return [{"sent": 2, "received": 0, "packet-loss": 100, "status": "timeout"}]


def make_api():
    tables = make_tables()
    tables[("ip", "arp")].append(
        {
            "address": "192.168.0.1",
            "mac-address": "4C:5E:0C:11:22:33",
            "interface": "ether1",
            "dynamic": True,
            "complete": True,
        }
    )
    commands = make_commands()
    commands["/ping"] = respond
    return FakeApi(tables, commands)


class ApConnector(FakeConnector):
    def __init__(self, ip, tid):
        super().__init__(ip, tid)
        self.api = make_api()

    def open_additional(self, timeout=None):
        return make_api()


def test_ap_probe_finds_the_replying_address_and_its_vendor(monkeypatch):
    monkeypatch.setattr(settings, "ap_probe_peers", ["10.10.10.2", "192.168.0.1", "192.168.1.1"])
    live = collect_live("10.229.2.50", "10047", connector_cls=ApConnector)
    probe = live["ap_probe"]["data"]
    assert probe["found"] == ["192.168.0.1"]
    peers = {p["ip"]: p for p in probe["peers"]}
    assert peers["192.168.0.1"]["avg_ms"] == 3.0
    assert peers["192.168.0.1"]["mac"] == "4C:5E:0C:11:22:33"
    assert peers["192.168.0.1"]["vendor"] == "MikroTik"
    assert peers["10.10.10.2"]["reachable"] is False
    assert peers["10.10.10.2"]["mac"] is None


def test_ap_probe_ignores_invalid_addresses(monkeypatch):
    monkeypatch.setattr(settings, "ap_probe_peers", ["not-an-ip", "192.168.0.1"])
    live = collect_live("10.229.2.50", "10047", connector_cls=ApConnector)
    assert [p["ip"] for p in live["ap_probe"]["data"]["peers"]] == ["192.168.0.1"]