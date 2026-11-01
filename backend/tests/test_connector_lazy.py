import threading

import pytest

from app.core.config import Account, settings
from app.core.errors import ConnectionFailed, FailureKind
from app.devices import customer_router as cr
from app.devices.customer_router import CustomerRouterConnector
from app.devices.hints import HintCache

TEST_IP = "10.229.2.50"


@pytest.fixture(autouse=True)
def cfg(monkeypatch):
    monkeypatch.setattr(settings, "api_ports", [2299, 8728])
    monkeypatch.setattr(settings, "allowed_networks", ["10.229.0.0/16"])
    monkeypatch.setattr(settings, "tid_username_template", "{tid}HKB")
    monkeypatch.setattr(settings, "tid_password_template", "pw{tid}")
    monkeypatch.setattr(
        settings,
        "fallback_accounts",
        [
            Account(username="bmw", password="b"),
            Account(username="HKB", password="x"),
            Account(username="bens", password="n"),
            Account(username="admin", password=""),
        ],
    )


class FakeProber:
    def __init__(self, states):
        self.states = states
        self.asked = []
        self.closed = False

    def state(self, port):
        self.asked.append(port)
        return self.states.get(port)

    def close(self):
        self.closed = True


def test_an_open_preferred_port_never_waits_for_the_other_one():
    prober = FakeProber({2299: None, 8728: FailureKind.TIMEOUT})

    def fake(**kw):
        return object()

    CustomerRouterConnector(TEST_IP, "10047", connect_fn=fake, probe_fn=lambda ip, ports: prober).connect()
    assert prober.asked == [2299]
    assert prober.closed is True


def test_all_ports_down_fails_without_any_login():
    prober = FakeProber({2299: FailureKind.TIMEOUT, 8728: FailureKind.PORT_CLOSED})
    calls = []

    def fake(**kw):
        calls.append(kw)
        return object()

    conn = CustomerRouterConnector(TEST_IP, "10047", connect_fn=fake, probe_fn=lambda ip, ports: prober)
    with pytest.raises(ConnectionFailed) as caught:
        conn.connect()
    assert calls == []
    assert prober.asked == [2299, 8728]
    assert {a.kind for a in caught.value.attempts} == {FailureKind.TIMEOUT, FailureKind.PORT_CLOSED}


def test_the_login_order_is_tid_bmw_hkb_bens_admin():
    calls = []

    def fake(**kw):
        calls.append(kw["username"])
        raise Exception("invalid login")

    conn = CustomerRouterConnector(TEST_IP, "10047", connect_fn=fake)
    with pytest.raises(ConnectionFailed):
        conn.connect()
    users = []
    for name in calls:
        if name not in users:
            users.append(name)
    assert users == ["10047HKB", "bmw", "HKB", "bens", "admin"]


def test_it_stops_at_the_first_account_that_works():
    calls = []

    def fake(**kw):
        calls.append((kw["username"], kw["port"]))
        if kw["username"] == "bmw":
            return object()
        raise Exception("invalid login")

    conn = CustomerRouterConnector(TEST_IP, "10047", connect_fn=fake).connect()
    assert conn.used.username == "bmw"
    assert [name for name, _ in calls][-1] == "bmw"
    assert "HKB" not in [name for name, _ in calls]


def test_a_fallback_account_hint_is_shared_between_technical_ids():
    hints = HintCache(60)

    def make(calls):
        def fake(**kw):
            calls.append((kw["username"], kw["port"]))
            if kw["username"] == "HKB" and kw["port"] == 2299:
                return object()
            raise Exception("invalid login")

        return fake

    CustomerRouterConnector(TEST_IP, "1001", connect_fn=make([]), hints=hints).connect()
    second = []
    CustomerRouterConnector(TEST_IP, "2002", connect_fn=make(second), hints=hints).connect()
    assert second == [("HKB", 2299)]


def test_a_technical_id_account_hint_stays_with_its_technical_id():
    hints = HintCache(60)

    def fake(**kw):
        return object()

    CustomerRouterConnector(TEST_IP, "1001", connect_fn=fake, hints=hints).connect()
    calls = []

    def other(**kw):
        calls.append(kw["username"])
        return object()

    CustomerRouterConnector(TEST_IP, "2002", connect_fn=other, hints=hints).connect()
    assert calls == ["2002HKB"]


def test_the_state_of_a_fast_port_does_not_wait_for_a_slow_one(monkeypatch):
    release = threading.Event()

    def fake_check(ip, port, timeout):
        if port == 8728:
            release.wait(5)
            return FailureKind.TIMEOUT
        return None

    monkeypatch.setattr(cr, "_check_port", fake_check)
    prober = cr.PortProber(TEST_IP, [2299, 8728], timeout=1)
    assert prober.state(2299) is None
    release.set()
    assert prober.state(8728) == FailureKind.TIMEOUT
    prober.close()