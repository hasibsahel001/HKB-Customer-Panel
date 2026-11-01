import pytest

from app.core.config import settings
from app.services.analysis import Status, classify_ccq, classify_chain


@pytest.fixture(autouse=True)
def thresholds(monkeypatch):
    monkeypatch.setattr(settings, "ccq_normal_percent", 70.0)
    monkeypatch.setattr(settings, "ccq_serious_percent", 50.0)
    monkeypatch.setattr(settings, "ccq_critical_percent", 35.0)
    monkeypatch.setattr(settings, "signal_normal_dbm", -60.0)
    monkeypatch.setattr(settings, "signal_warning_dbm", -70.0)
    monkeypatch.setattr(settings, "signal_serious_dbm", -80.0)


@pytest.mark.parametrize(
    "percent, expected",
    [
        (95, Status.NORMAL),
        (70, Status.NORMAL),
        (69, Status.WARNING),
        (63, Status.WARNING),
        (50, Status.WARNING),
        (49, Status.SERIOUS),
        (35, Status.SERIOUS),
        (34, Status.CRITICAL),
        (26, Status.CRITICAL),
        (None, Status.UNKNOWN),
    ],
)
def test_classify_ccq(percent, expected):
    assert classify_ccq(percent) == expected


def test_chain_uses_the_worse_direction():
    assert classify_chain(-52, -50) == Status.NORMAL
    assert classify_chain(-52, -85) == Status.CRITICAL
    assert classify_chain(None, -65) == Status.WARNING
    assert classify_chain(None, None) == Status.UNKNOWN