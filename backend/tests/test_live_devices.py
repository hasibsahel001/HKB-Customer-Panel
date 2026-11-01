import pytest
from fakes import FakeApi, make_commands, make_tables

from app.core.config import settings
from app.core.errors import ConnectionFailed
from app.services import live_devices as ld
from app.services.devices import collect_devices, lan_exclusions
from app.services.filtering import HIDDEN_FINDING_CODES, hide_findings
from app.services.live_devices import DeviceSessions


class Conn:
    """A connector whose API can be swapped, to test reconnecting."""

    created = 0

    def __init__(self, ip, tid, tables=None):
        Conn.created += 1
        self.ip, self.tid = ip, tid
        self.api = FakeApi(tables or make_tables(), make_commands())
        self.closed = False

    def connect(self):
        return self

    def close(self):
        self.closed = True


def arp(ip, mac, interface="ether1", **flags):
    row = {"address": ip, "mac-address": mac, "interface": interface, "dynamic": True, "complete": True}
    row.update(flags)
    return row


def collect(tables, **kw):
    api = FakeApi(tables, make_commands())
    return collect_devices(
        api,
        queues=None,
        lease_by_ip=kw.get("leases", {}),
        lan_interfaces=kw.get("lan", ["ether1"]),
        server_interfaces=kw.get("servers", {}),
        exclude=lan_exclusions(api) if kw.get("detect", True) else set(),
    )


def tables_with_arp(*rows):
    tables = make_tables()
    tables[("ip", "arp")] = list(rows)
    return tables


@pytest.fixture(autouse=True)
def cfg(monkeypatch):
    monkeypatch.setattr(settings, "ap_probe_peers", ["10.10.10.2"])
    Conn.created = 0


def test_devices_on_a_non_dhcp_interface_are_counted():
    tables = tables_with_arp(arp("10.10.10.5", "AA:00:00:00:00:01", "bridge1"))
    devices = collect(tables, lan=["ether1"])
    assert [d["ip"] for d in devices] == ["10.10.10.5"]


def test_the_uplink_is_never_a_device():
    tables = tables_with_arp(
        arp("10.10.10.5", "AA:00:00:00:00:01", "ether1"),
        arp("10.229.255.1", "AA:00:00:00:00:02", "wlan1"),
        arp("10.229.255.2", "AA:00:00:00:00:03", "H-PPPoE"),
    )
    assert [d["ip"] for d in collect(tables)] == ["10.10.10.5"]


def test_without_uplink_information_only_the_dhcp_interface_counts():
    tables = tables_with_arp(
        arp("10.10.10.5", "AA:00:00:00:00:01", "ether1"),
        arp("10.20.20.5", "AA:00:00:00:00:02", "ether2"),
    )
    tables[("interface", "pppoe-client")] = []
    assert [d["ip"] for d in collect(tables, lan=["ether1"])] == ["10.10.10.5"]


def test_static_ip_devices_are_counted_but_unresolved_entries_are_not():
    tables = tables_with_arp(
        arp("10.10.10.5", "AA:00:00:00:00:01", dynamic=False),
        arp("10.10.10.6", "AA:00:00:00:00:02", dynamic=False, complete=False),
        arp("10.10.10.7", "AA:00:00:00:00:03", complete=False),
        arp("10.10.10.8", "AA:00:00:00:00:04", invalid=True),
        arp("10.10.10.9", "AA:00:00:00:00:05", disabled=True),
    )
    assert [d["ip"] for d in collect(tables)] == ["10.10.10.5"]


def test_a_fresh_lease_counts_before_arp_catches_up():
    tables = tables_with_arp(arp("10.10.10.5", "AA:00:00:00:00:01"))
    leases = {
        "10.10.10.20": {
            "ip": "10.10.10.20", "mac_address": "AA:00:00:00:00:20", "hostname": "new-phone",
            "status": "bound", "server": "dhcp1", "last_seen_seconds": 12, "disabled": False,
        },
        "10.10.10.21": {  # a lease that has been quiet for a long time is not online
            "ip": "10.10.10.21", "mac_address": "AA:00:00:00:00:21", "hostname": "old",
            "status": "bound", "server": "dhcp1", "last_seen_seconds": 4000, "disabled": False,
        },
    }
    devices = collect(tables, leases=leases, servers={"dhcp1": "ether1"})
    assert [d["ip"] for d in devices] == ["10.10.10.5", "10.10.10.20"]
    assert devices[1]["source"] == "dhcp"
    assert devices[1]["hostname"] == "new-phone"


def test_duplicate_ips_are_listed_once():
    tables = tables_with_arp(arp("10.10.10.5", "AA:00:00:00:00:01"), arp("10.10.10.5", "AA:00:00:00:00:01"))
    assert len(collect(tables)) == 1


def test_session_reuses_one_connection_and_hides_the_access_point(monkeypatch):
    tables = tables_with_arp(
        arp("10.10.10.5", "AA:00:00:00:00:01"),
        arp("10.10.10.2", "AA:00:00:00:00:02"),  # the customer's own access point
    )
    clock = {"t": 100.0}
    sessions = DeviceSessions(lambda ip, tid: Conn(ip, tid, tables), clock=lambda: clock["t"])
    monkeypatch.setattr(sessions, "_start_reaper", lambda: None)

    first = sessions.read("10.229.2.50", "10047")
    assert [d["ip"] for d in first["devices"]] == ["10.10.10.5"]
    assert first["count"] == 1
    assert first["total_traffic"]["upload_bps"] == 1000

    clock["t"] += 0.1  # inside MIN_INTERVAL: shared reading
    assert sessions.read("10.229.2.50", "10047") is first

    clock["t"] += 2.0
    again = sessions.read("10.229.2.50", "10047")
    assert again is not first
    assert Conn.created == 1

def test_live_read_includes_the_wireless_signal_and_ccq(monkeypatch):
    tables = tables_with_arp(arp("10.10.10.5", "AA:00:00:00:00:01"))
    sessions = DeviceSessions(lambda ip, tid: Conn(ip, tid, tables))
    monkeypatch.setattr(sessions, "_start_reaper", lambda: None)

    wireless = sessions.read("10.229.2.50", "10047")["wireless"]
    reg = wireless["registration"]
    assert wireless["interface"] == "wlan1"
    assert reg["signal_dbm"] == -50
    assert reg["tx_ccq"] == 70 and reg["rx_ccq"] == 95
    assert wireless["analysis"]["overall"] in {"normal", "warning", "serious", "critical", "unknown"}
    assert len(wireless["analysis"]["chains"]) == 2


def test_a_router_without_wireless_still_lists_devices(monkeypatch):
    tables = tables_with_arp(arp("10.10.10.5", "AA:00:00:00:00:01"))
    del tables[("interface", "wireless")]
    sessions = DeviceSessions(lambda ip, tid: Conn(ip, tid, tables))
    monkeypatch.setattr(sessions, "_start_reaper", lambda: None)

    result = sessions.read("10.229.2.50", "10047")
    assert result["wireless"] is None
    assert result["count"] == 1


def test_session_reconnects_when_the_connection_goes_stale(monkeypatch):
    clock = {"t": 100.0}
    made = []

    def factory(ip, tid):
        conn = Conn(ip, tid, tables_with_arp(arp("10.10.10.5", "AA:00:00:00:00:01")))
        made.append(conn)
        return conn

    sessions = DeviceSessions(factory, clock=lambda: clock["t"])
    monkeypatch.setattr(sessions, "_start_reaper", lambda: None)
    sessions.read("10.229.2.50", "10047")

    def broken(*parts):
        raise OSError("connection reset")

    made[0].api.path = broken
    clock["t"] += 5
    result = sessions.read("10.229.2.50", "10047")
    assert result["count"] == 1
    assert len(made) == 2 and made[0].closed


def test_connection_failures_are_not_swallowed(monkeypatch):
    def factory(ip, tid):
        raise ConnectionFailed([])

    sessions = DeviceSessions(factory)
    monkeypatch.setattr(sessions, "_start_reaper", lambda: None)
    with pytest.raises(ConnectionFailed):
        sessions.read("10.229.2.50", "10047")


def test_idle_connections_are_closed(monkeypatch):
    clock = {"t": 100.0}
    made = []

    def factory(ip, tid):
        conn = Conn(ip, tid)
        made.append(conn)
        return conn

    sessions = DeviceSessions(factory, clock=lambda: clock["t"])
    monkeypatch.setattr(sessions, "_start_reaper", lambda: None)
    sessions.read("10.229.2.50", "10047")
    assert sessions.reap() == 0
    clock["t"] += ld.IDLE_SECONDS + 1
    assert sessions.reap() == 1
    assert made[0].closed


def test_near_limit_findings_are_never_shown():
    assert "queue_near_limit" in HIDDEN_FINDING_CODES
    diagnostics = {
        "overall": "warning",
        "count": 2,
        "findings": [
            {"code": "queue_near_limit", "severity": "warning"},
            {"code": "cpu_high", "severity": "serious"},
        ],
    }
    result = hide_findings(diagnostics)
    assert [f["code"] for f in result["findings"]] == ["cpu_high"]
    assert result["overall"] == "serious"


def test_devices_endpoint(client, monkeypatch):
    from app.api import customer as customer_module

    tables = tables_with_arp(arp("10.10.10.5", "AA:00:00:00:00:01"))
    sessions = DeviceSessions(lambda ip, tid: Conn(ip, tid, tables))
    monkeypatch.setattr(sessions, "_start_reaper", lambda: None)
    monkeypatch.setattr(customer_module, "DEVICE_SESSIONS", sessions)

    password = "correct-horse-1"
    assert client.post(
        "/api/setup", json={"username": "boss", "password": password, "password_confirm": password}
    ).status_code == 201
    login = client.post("/api/auth/login", json={"username": "boss", "password": password})
    headers = {"X-CSRF-Token": login.json()["csrf_token"]}

    response = client.post("/api/customer/devices", json={"ip": "10.229.2.50", "tid": "10047"}, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["count"] == 1

    bad = client.post("/api/customer/devices", json={"ip": "8.8.8.8", "tid": "10047"}, headers=headers)
    assert bad.status_code == 422

    anonymous = client.post("/api/customer/devices", json={"ip": "10.229.2.50", "tid": "10047"})
    assert anonymous.status_code in (401, 403)