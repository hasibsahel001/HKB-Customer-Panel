import pytest

from app.core.config import settings
from app.services.analysis import Status
from app.services.connectivity import classify_ping, parse_rtt_ms, summarize_ping


@pytest.fixture(autouse=True)
def thresholds(monkeypatch):
    monkeypatch.setattr(settings, "ping_loss_warning_percent", 2.0)
    monkeypatch.setattr(settings, "ping_loss_serious_percent", 10.0)
    monkeypatch.setattr(settings, "ping_latency_warning_ms", 80.0)
    monkeypatch.setattr(settings, "ping_latency_serious_ms", 200.0)


@pytest.mark.parametrize(
    "value, expected",
    [
        ("12ms", 12.0),
        ("1ms500us", 1.5),
        ("800us", 0.8),
        ("1s", 1000.0),
        (12, 12.0),
        (None, None),
        ("abc", None),
        ("12", None),
    ],
)
def test_parse_rtt_ms(value, expected):
    assert parse_rtt_ms(value) == pytest.approx(expected) if expected is not None else parse_rtt_ms(value) is None


def test_summarize_ping_uses_last_row():
    rows = [
        {"host": "8.8.8.8", "sent": 1, "received": 1, "packet-loss": 0, "avg-rtt": "10ms", "min-rtt": "10ms", "max-rtt": "10ms", "time": "10ms"},
        {"host": "8.8.8.8", "sent": 2, "received": 2, "packet-loss": 0, "avg-rtt": "11ms", "min-rtt": "10ms", "max-rtt": "12ms", "time": "12ms"},
    ]
    summary = summarize_ping(rows)
    assert summary["sent"] == 2
    assert summary["received"] == 2
    assert summary["loss_percent"] == 0.0
    assert summary["avg_ms"] == 11.0
    assert summary["max_ms"] == 12.0
    assert summary["reachable"] is True


def test_summarize_ping_computes_loss_when_missing():
    rows = [{"sent": 4, "received": 3, "time": "20ms"}]
    summary = summarize_ping(rows)
    assert summary["loss_percent"] == 25.0
    assert summary["avg_ms"] == 20.0


def test_summarize_ping_all_lost():
    rows = [{"sent": 4, "received": 0, "packet-loss": 100, "status": "timeout"}]
    summary = summarize_ping(rows)
    assert summary["reachable"] is False
    assert summary["avg_ms"] is None


def test_summarize_ping_empty():
    assert summarize_ping([]) is None


@pytest.mark.parametrize(
    "summary, expected",
    [
        (None, Status.UNKNOWN),
        ({"reachable": None}, Status.UNKNOWN),
        ({"reachable": False}, Status.CRITICAL),
        ({"reachable": True, "loss_percent": 0.0, "avg_ms": 20.0}, Status.NORMAL),
        ({"reachable": True, "loss_percent": 5.0, "avg_ms": 20.0}, Status.WARNING),
        ({"reachable": True, "loss_percent": 25.0, "avg_ms": 20.0}, Status.SERIOUS),
        ({"reachable": True, "loss_percent": 0.0, "avg_ms": 120.0}, Status.WARNING),
        ({"reachable": True, "loss_percent": 0.0, "avg_ms": 250.0}, Status.SERIOUS),
    ],
)
def test_classify_ping(summary, expected):
    assert classify_ping(summary) == expected