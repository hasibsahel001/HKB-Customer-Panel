from types import SimpleNamespace


class FakeApi:
    """A tiny stand-in for a librouteros connection."""

    def __init__(self, tables, commands):
        self.tables = tables
        self.commands = commands
        self.closed = False

    def path(self, *parts):
        if parts not in self.tables:
            raise KeyError(parts)
        return list(self.tables[parts])

    def rawCmd(self, cmd, *words):
        handler = self.commands.get(cmd)
        if handler is None:
            raise RuntimeError(f"no handler for {cmd}")
        return iter(handler(words) if callable(handler) else handler)

    def close(self):
        self.closed = True


def make_tables():
    return {
        ("system", "identity"): [{"name": "R-Test"}],
        ("system", "resource"): [
            {
                "board-name": "LHG 5",
                "version": "6.49.19",
                "uptime": "5w1d17h",
                "cpu-load": 9,
                "total-memory": 100,
                "free-memory": 60,
                "architecture-name": "mipsbe",
            }
        ],
        ("system", "health"): [],
        ("interface",): [
            {
                "name": "ether1",
                "type": "ether",
                "running": True,
                "disabled": False,
                "rx-byte": 10,
                "tx-byte": 20,
                "link-downs": 2,
            }
        ],
        ("interface", "wireless"): [
            {"name": "wlan1", "running": True, "disabled": False, "ssid": "HB", "frequency": 5610}
        ],
        ("interface", "wireless", "registration-table"): [
            {
                "interface": "wlan1",
                "mac-address": "AA:BB:CC:DD:EE:FF",
                "radio-name": "HKB-1739",
                "signal-strength": "-50@HT20",
                "signal-to-noise": 40,
                "tx-ccq": 70,
                "rx-ccq": 95,
                "tx-signal-strength-ch0": -52,
                "signal-strength-ch0": -50,
                "tx-signal-strength-ch1": -50,
                "signal-strength-ch1": -44,
                "uptime": "1w",
            }
        ],
        ("ip", "dhcp-server"): [{"name": "dhcp1", "interface": "ether1", "disabled": False}],
        ("ip", "dhcp-server", "lease"): [
            {
                "address": "10.10.10.5",
                "mac-address": "5E:41:4B:6A:9A:90",
                "host-name": "phone",
                "status": "bound",
            }
        ],
        ("ip", "arp"): [
            {
                "address": "10.10.10.5",
                "mac-address": "5E:41:4B:6A:9A:90",
                "interface": "ether1",
                "dynamic": True,
                "complete": True,
            }
        ],
        ("queue", "simple"): [
            {
                "name": "host-queue",
                "target": "10.10.10.5/32",
                "parent": "none",
                "disabled": False,
                "max-limit": "2M/2M",
                "rate": "0/0",
            }
        ],
        ("interface", "pppoe-client"): [
            {"name": "H-PPPoE", "user": "user1", "running": True, "disabled": False, "interface": "wlan1"}
        ],
        ("ip", "address"): [],
    }


def make_commands():
    return {
        "/interface/ethernet/monitor": [{"rate": "100Mbps", "full-duplex": True, "status": "link-ok"}],
        "/interface/monitor-traffic": [{"rx-bits-per-second": 1000, "tx-bits-per-second": 2000}],
        "/interface/pppoe-client/monitor": [
            {
                "status": "connected",
                "uptime": "41m19s",
                "local-address": "10.229.2.50",
                "remote-address": "10.229.255.100",
            }
        ],
        "/ping": [
            {"host": "8.8.8.8", "sent": 1, "received": 1, "packet-loss": 0, "avg-rtt": "20ms", "time": "20ms"},
            {"host": "8.8.8.8", "sent": 2, "received": 2, "packet-loss": 0, "avg-rtt": "21ms", "time": "22ms"},
        ],
        "/tool/mac-ping": [{"time": "2ms"}, {"time": "4ms"}],
    }


class FakeConnector:
    def __init__(self, ip, tid):
        self.ip = ip
        self.tid = tid
        self.api = FakeApi(make_tables(), make_commands())
        self.used = SimpleNamespace(account_index=0, port=2299)
        self.failures = []
        self.login_attempts = 1
        self.extras = []

    def connect(self):
        return self

    def close(self):
        self.api.close()

    def open_additional(self, timeout=None):
        extra = FakeApi(make_tables(), make_commands())
        self.extras.append(extra)
        return extra


class NoExtraConnector(FakeConnector):
    def open_additional(self, timeout=None):
        raise RuntimeError("the router refused another connection")