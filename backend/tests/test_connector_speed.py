import pytest

from app.core.config import Account, settings
from app.core.errors import ConnectionFailed, FailureKind
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
        [Account(username="HKB", password="x"), Account(username="admin", password="")],
    )


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_hint_cache_expiry_and_forget():
    clock = Clock()
    cache = HintCache(60, clock=clock)
    cache.put("1.1.1.1", "5", (1, 2299))
    assert cache.get("1.1.1.1", "5") == (1, 2299)
    assert cache.get("1.1.1.1", "6") is None
    clock.now = 61
    assert cache.get("1.1.1.1", "5") is None
    cache.put("1.1.1.1", "5", (0, 2299))
    cache.forget("1.1.1.1", "5")
    assert cache.get("1.1.1.1", "5") is None


def test_closed_ports_are_skipped_before_any_login():
    calls = []

    def probe(ip, ports):
        return {2299: None, 8728: FailureKind.PORT_CLOSED}

    def fake(**kw):
        calls.append((kw["username"], kw["port"]))
        if kw["username"] == "HKB":
            return object()
        raise Exception("invalid login")

    conn = CustomerRouterConnector(TEST_IP, "10047", connect_fn=fake, probe_fn=probe).connect()
    assert calls == [("10047HKB", 2299), ("HKB", 2299)]
    assert conn.login_attempts == 2


def test_all_ports_closed_fails_without_logging_in():
    calls = []

    def probe(ip, ports):
        return {2299: FailureKind.TIMEOUT, 8728: FailureKind.PORT_CLOSED}

    def fake(**kw):
        calls.append(kw)
        return object()

    conn = CustomerRouterConnector(TEST_IP, "10047", connect_fn=fake, probe_fn=probe)
    with pytest.raises(ConnectionFailed) as caught:
        conn.connect()
    assert calls == []
    assert {a.kind for a in caught.value.attempts} == {FailureKind.TIMEOUT, FailureKind.PORT_CLOSED}


def test_hint_is_tried_first_on_the_second_check():
    hints = HintCache(60)
    first_calls, second_calls = [], []

    def make(calls):
        def fake(**kw):
            calls.append((kw["username"], kw["port"]))
            if kw["username"] == "HKB" and kw["port"] == 2299:
                return object()
            raise Exception("invalid login")

        return fake

    CustomerRouterConnector(TEST_IP, "10047", connect_fn=make(first_calls), hints=hints).connect()
    assert first_calls[0] == ("10047HKB", 2299)
    assert first_calls[-1] == ("HKB", 2299)

    CustomerRouterConnector(TEST_IP, "10047", connect_fn=make(second_calls), hints=hints).connect()
    assert second_calls == [("HKB", 2299)]


def test_new_technical_id_still_follows_the_exact_order():
    hints = HintCache(60)
    hints.put(TEST_IP, "10047", (1, 2299))
    calls = []

    def fake(**kw):
        calls.append((kw["username"], kw["port"]))
        return object()

    CustomerRouterConnector(TEST_IP, "99999", connect_fn=fake, hints=hints).connect()
    assert calls == [("99999HKB", 2299)]


def test_failed_hint_falls_back_and_is_forgotten():
    hints = HintCache(60)
    hints.put(TEST_IP, "10047", (1, 2299))

    def fake(**kw):
        raise Exception("invalid login")

    conn = CustomerRouterConnector(TEST_IP, "10047", connect_fn=fake, hints=hints)
    with pytest.raises(ConnectionFailed):
        conn.connect()
    assert hints.get(TEST_IP, "10047") is None


def test_open_additional_reuses_the_working_account():
    calls = []

    def fake(**kw):
        calls.append((kw["username"], kw["port"]))
        if kw["username"] == "HKB":
            return object()
        raise Exception("invalid login")

    conn = CustomerRouterConnector(TEST_IP, "10047", connect_fn=fake).connect()
    calls.clear()
    conn.open_additional()
    assert calls == [("HKB", 2299)]