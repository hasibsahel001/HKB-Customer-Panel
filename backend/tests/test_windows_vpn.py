import subprocess

import pytest

from app.core.config import settings
from app.core.errors import InvalidInput
from app.services import windows_vpn as wv


def completed(stdout="", returncode=0, stderr=""):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


@pytest.fixture(autouse=True)
def cfg(monkeypatch):
    monkeypatch.setattr(settings, "ap_probe_peers", ["10.10.10.2", "192.168.0.1"])
    monkeypatch.setattr(settings, "vpn_connection_name", "VPN")


def test_nothing_is_done_when_the_panel_is_not_on_windows():
    calls = []
    result = wv.apply_pptp("10.229.1.1", "10.10.10.2", runner=lambda *a, **k: calls.append(a), platform="linux")
    assert result["supported"] is False
    assert calls == []


def test_values_go_through_the_environment_never_the_command_line():
    seen = {}

    def runner(args, **kw):
        seen["args"], seen["env"] = args, kw["env"]
        return completed("STATE=created\nCONNECTED=1\n")

    result = wv.apply_pptp("10.229.1.1", "192.168.0.1", runner=runner, platform="win32")
    assert result == {
        "supported": True, "name": "VPN", "server": "10.229.1.1",
        "state": "created", "connected": True, "message": None, "credentials_saved": False,
    }
    assert seen["args"][0] == "powershell"
    assert "10.229.1.1" not in " ".join(seen["args"])
    assert seen["env"]["HKB_VPN_SERVER"] == "10.229.1.1"
    assert seen["env"]["HKB_VPN_AP"] == "192.168.0.1"
    assert seen["env"]["HKB_VPN_USER"] == "1" and seen["env"]["HKB_VPN_PASS"] == "1"


def test_a_failed_connect_is_reported_but_the_entry_is_kept():
    out = "STATE=updated\nCONNECTED=0\nMESSAGE=Remote Access error 619\n"
    result = wv.apply_pptp("10.229.1.1", "10.10.10.2", runner=lambda *a, **k: completed(out), platform="win32")
    assert result["state"] == "updated"
    assert result["connected"] is False
    assert "619" in result["message"]


def test_auto_connect_can_be_turned_off():
    result = wv.apply_pptp(
        "10.229.1.1", "10.10.10.2", connect=False, runner=lambda *a, **k: completed("STATE=updated\n"), platform="win32"
    )
    assert result["connected"] is None


def test_bad_input_is_refused_before_anything_runs():
    def runner(*a, **k):
        raise AssertionError("must not run")

    with pytest.raises(InvalidInput):
        wv.apply_pptp("not-an-ip", "10.10.10.2", runner=runner, platform="win32")
    with pytest.raises(InvalidInput):
        wv.apply_pptp("10.229.1.1", "8.8.8.8", runner=runner, platform="win32")


def test_a_powershell_error_becomes_vpn_setup_failed():
    with pytest.raises(wv.VpnSetupFailed):
        wv.apply_pptp(
            "10.229.1.1", "10.10.10.2", runner=lambda *a, **k: completed(returncode=1, stderr="boom"), platform="win32"
        )


def test_saved_credentials_are_reported():
    out = "STATE=updated\nCREDS=1\n"
    result = wv.apply_pptp("10.229.1.1", "10.10.10.2", connect=False, runner=lambda *a, **k: completed(out), platform="win32")
    assert result["credentials_saved"] is True
    assert result["connected"] is None