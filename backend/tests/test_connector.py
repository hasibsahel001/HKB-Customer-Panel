import pytest

from app.core.config import Account, settings
from app.core.errors import ConnectionFailed, InvalidInput
from app.devices.credentials import build_attempts
from app.devices.customer_router import CustomerRouterConnector
from app.devices.validation import validate_target_ip

TEST_IP = "10.229.2.50"


@pytest.fixture(autouse=True)
def cfg(monkeypatch):
    """Isolate tests from the real .env file."""
    monkeypatch.setattr(settings, "api_ports", [2299, 8728])
    monkeypatch.setattr(settings, "allowed_networks", ["10.229.0.0/16"])
    monkeypatch.setattr(settings, "tid_username_template", "{tid}HKB")
    monkeypatch.setattr(settings, "tid_password_template", "pw{tid}")
    monkeypatch.setattr(
        settings,
        "fallback_accounts",
        [
            Account(username="HKB", password="x"),
            Account(username="admin", password=""),
        ],
    )


def test_credential_generation_and_order():
    a = build_attempts("10047")
    assert (a[0].username, a[0].password, a[0].port) == ("10047HKB", "pw10047", 2299)
    assert (a[1].username, a[1].port) == ("10047HKB", 8728)
    assert (a[2].username, a[2].port) == ("HKB", 2299)
    assert (a[3].username, a[3].port) == ("HKB", 8728)
    assert a[4].username == "admin" and a[4].password == ""
    assert a[4].port == 2299 and a[5].port == 8728


def test_stops_after_first_success_and_skips_closed_port():
    """Port 2299 is closed; the first account is rejected on 8728; HKB connects on 8728."""
    calls = []

    def fake(**kw):
        calls.append((kw["username"], kw["port"]))
        if kw["port"] == 2299:
            raise ConnectionRefusedError()
        if kw["username"] == "HKB":
            return object()
        raise Exception("invalid login")

    c = CustomerRouterConnector(TEST_IP, "10047", connect_fn=fake).connect()
    assert c.used.username == "HKB" and c.used.port == 8728
    assert calls == [("10047HKB", 2299), ("10047HKB", 8728), ("HKB", 8728)]


def test_auth_failure_does_not_skip_port():
    """A rejected login must not disable the port; the next account is tried on the same port."""
    calls = []

    def fake(**kw):
        calls.append((kw["username"], kw["port"]))
        if kw["username"] == "HKB" and kw["port"] == 2299:
            return object()
        raise Exception("invalid login")

    c = CustomerRouterConnector(TEST_IP, "10047", connect_fn=fake).connect()
    assert c.used.username == "HKB" and c.used.port == 2299
    assert calls == [("10047HKB", 2299), ("10047HKB", 8728), ("HKB", 2299)]
    assert ("admin", 2299) not in calls


def test_all_fail_raises_without_passwords():
    def fake(**kw):
        raise TimeoutError()

    c = CustomerRouterConnector(TEST_IP, "10047", connect_fn=fake)
    with pytest.raises(ConnectionFailed):
        c.connect()
    assert len(c.failures) > 0
    assert all(not hasattr(f, "password") for f in c.failures)


@pytest.mark.parametrize(
    "bad", ["abc", "127.0.0.1", "8.8.8.8", "224.0.0.1", "192.168.2.50", ""]
)
def test_ip_validation_rejects(bad):
    with pytest.raises(InvalidInput):
        validate_target_ip(bad)


def test_ip_validation_accepts():
    assert validate_target_ip("10.229.2.50") == "10.229.2.50"