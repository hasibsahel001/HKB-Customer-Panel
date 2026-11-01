from app.services.usage import clamp_seconds, lan_interface, sample_usage


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class FakeApi:
    def __init__(self, dhcp=None, rates=None, fail_at=()):
        self.dhcp = dhcp if dhcp is not None else [{"interface": "ether1", "disabled": False}]
        self.rates = rates or [(1000, 2000)]
        self.fail_at = set(fail_at)
        self.calls = 0
        self.interfaces = []

    def path(self, *parts):
        assert parts == ("ip", "dhcp-server")
        return list(self.dhcp)

    def rawCmd(self, cmd, *words):
        assert cmd == "/interface/monitor-traffic"
        self.interfaces.append(words[0])
        index = self.calls
        self.calls += 1
        if index in self.fail_at:
            raise RuntimeError("busy")
        up, down = self.rates[min(index, len(self.rates) - 1)]
        return iter([{"rx-bits-per-second": up, "tx-bits-per-second": down}])


def test_clamp():
    assert clamp_seconds(10) == 10
    assert clamp_seconds(1) == 3
    assert clamp_seconds(500) == 30
    assert clamp_seconds("x") == 10
    assert clamp_seconds(None) == 10


def test_lan_interface_prefers_the_enabled_dhcp_server():
    assert lan_interface(FakeApi(dhcp=[{"interface": "bridge1", "disabled": False}])) == "bridge1"
    assert lan_interface(FakeApi(dhcp=[{"interface": "bridge1", "disabled": True}])) == "ether1"
    assert lan_interface(FakeApi(dhcp=[])) == "ether1"


def test_samples_are_one_second_apart_and_use_the_lan_interface():
    clock = Clock()
    api = FakeApi(dhcp=[{"interface": "bridge1", "disabled": False}], rates=[(1000, 2000), (3000, 500), (200, 9000)])
    result = sample_usage(api, 3, sleep=clock.sleep, clock=clock)
    assert result["interface"] == "bridge1"
    assert result["seconds"] == 3
    assert [s["elapsed_ms"] for s in result["samples"]] == [0, 1000, 2000]
    assert [s["up_bps"] for s in result["samples"]] == [1000, 3000, 200]
    assert [s["down_bps"] for s in result["samples"]] == [2000, 500, 9000]
    assert set(api.interfaces) == {"=interface=bridge1"}


def test_a_failed_sample_becomes_null_and_the_rest_continue():
    clock = Clock()
    api = FakeApi(fail_at={1})
    result = sample_usage(api, 3, sleep=clock.sleep, clock=clock)
    assert result["samples"][1]["up_bps"] is None
    assert result["samples"][2]["up_bps"] == 1000