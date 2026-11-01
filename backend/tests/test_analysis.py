import pytest

from app.core.config import settings
from app.services.analysis import (
    Status,
    classify_ccq,
    classify_signal,
    worst_status,
)


@pytest.fixture(autouse=True)
def thresholds(monkeypatch):
    monkeypatch.setattr(settings, "signal_normal_dbm", -60.0)
    monkeypatch.setattr(settings, "signal_warning_dbm", -70.0)
    monkeypatch.setattr(settings, "signal_serious_dbm", -80.0)
    monkeypatch.setattr(settings, "ccq_normal_percent", 80.0)
    monkeypatch.setattr(settings, "ccq_serious_percent", 60.0)


@pytest.mark.parametrize(
    "dbm, expected",
    [
        (-50, Status.NORMAL),
        (-60, Status.NORMAL),
        (-65, Status.WARNING),
        (-70, Status.WARNING),
        (-75, Status.SERIOUS),
        (-80, Status.SERIOUS),
        (-85, Status.CRITICAL),
        (None, Status.UNKNOWN),
    ],
)
def test_classify_signal(dbm, expected):
    assert classify_signal(dbm) == expected


@pytest.mark.parametrize(
    "percent, expected",
    [
        (95, Status.NORMAL),
        (80, Status.NORMAL),
        (79, Status.WARNING),
        (60, Status.WARNING),
        (59, Status.SERIOUS),
        (None, Status.UNKNOWN),
    ],
)
def test_classify_ccq(percent, expected):
    assert classify_ccq(percent) == expected


def test_worst_status():
    assert worst_status(Status.NORMAL, Status.SERIOUS) == Status.SERIOUS
    assert worst_status(Status.UNKNOWN, Status.NORMAL) == Status.NORMAL
    assert worst_status(Status.UNKNOWN, Status.UNKNOWN) == Status.UNKNOWN