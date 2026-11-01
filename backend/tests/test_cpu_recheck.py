import pytest

from app.core.config import settings
from app.services import snapshot as snap


class FakeResourceApi:
    def __init__(self, cpu_values):
        self.cpu_values = list(cpu_values)
        self.calls = 0

    def path(self, *parts):
        assert parts == ("system", "resource")
        cpu = self.cpu_values[min(self.calls, len(self.cpu_values) - 1)]
        self.calls += 1
        return [
            {
                "board-name": "LHG 5",
                "version": "6.49.19",
                "uptime": "1h",
                "cpu-load": cpu,
                "total-memory": 100,
                "free-memory": 60,
                "architecture-name": "mipsbe",
            }
        ]


@pytest.fixture(autouse=True)
def cfg(monkeypatch):
    monkeypatch.setattr(settings, "cpu_warning_percent", 80.0)
    monkeypatch.setattr(settings, "cpu_recheck_delay_seconds", 0.01)
    monkeypatch.setattr(snap.time, "sleep", lambda s: None)


def test_a_low_first_reading_is_used_as_is_without_a_second_call():
    api = FakeResourceApi([20])
    data = snap._resource(api, {})
    assert data["cpu_load"] == 20
    assert api.calls == 1


def test_a_high_first_reading_is_confirmed_with_a_second_read():
    api = FakeResourceApi([95, 22])
    data = snap._resource(api, {})
    assert data["cpu_load"] == 22
    assert api.calls == 2


def test_a_genuinely_sustained_high_load_still_reports_high():
    api = FakeResourceApi([95, 93])
    data = snap._resource(api, {})
    assert data["cpu_load"] == 93
    assert api.calls == 2


def test_a_recheck_failure_keeps_the_first_reading():
    class Flaky:
        def __init__(self):
            self.calls = 0

        def path(self, *parts):
            self.calls += 1
            if self.calls == 2:
                raise RuntimeError("boom")
            return [{"board-name": "x", "version": "6", "uptime": "1h", "cpu-load": 91,
                      "total-memory": 100, "free-memory": 50, "architecture-name": "mipsbe"}]

    data = snap._resource(Flaky(), {})
    assert data["cpu_load"] == 91