import pytest
from fakes_update import FakeUpdateApi

from app.core.errors import InvalidInput
from app.services import router_actions as ra


@pytest.mark.parametrize(
    "text, expected",
    [
        ("6.49.19", (6, 49, 19)),
        ("6.49.19 (long-term)", (6, 49, 19)),
        ("7.20.2", (7, 20, 2)),
        ("v7.1", (7, 1, 0)),
        ("", None),
        (None, None),
        ("abc", None),
    ],
)
def test_parse_version(text, expected):
    assert ra.parse_version(text) == expected


@pytest.mark.parametrize(
    "state, expected",
    [
        ({"installed": "6.49.7", "latest": "6.49.19", "status": "New version is available"}, "available"),
        ({"installed": "6.49.19", "latest": "6.49.19", "status": "System is already up to date"}, "up_to_date"),
        ({"installed": "6.49.19", "latest": "6.48.0", "status": "System is already up to date"}, "up_to_date"),
        ({"installed": "6.49.19", "latest": "7.20.2", "status": "New version is available"}, "major_change"),
        ({"installed": "6.49.7", "latest": None, "status": "ERROR: could not resolve dns name"}, "error"),
        ({"installed": "6.49.7", "latest": None, "status": "Cannot connect to the server"}, "error"),
        ({"installed": None, "latest": None, "status": ""}, "unknown"),
    ],
)
def test_classify_update(state, expected):
    assert ra.classify_update(state) == expected


def test_check_switches_the_channel_to_stable_and_reports_it():
    api = FakeUpdateApi(channel="long-term")
    result = ra.check_updates(api)
    assert result["channel"] == "stable"
    assert result["channel_changed_from"] == "long-term"
    assert result["state"] == "available"
    assert result["latest"] == "6.49.19"
    assert "/system/package/update/set" in api.names()
    assert "/system/package/update/check-for-updates" in api.names()


def test_check_leaves_a_stable_channel_alone():
    api = FakeUpdateApi(channel="stable")
    result = ra.check_updates(api)
    assert result["channel_changed_from"] is None
    assert "/system/package/update/set" not in api.names()


def test_firmware_info_cases():
    pending = ra.firmware_info(FakeUpdateApi())
    assert pending["supported"] is True and pending["pending"] is True
    assert pending["current"] == "6.45" and pending["upgrade"] == "6.49.19"

    same = ra.firmware_info(
        FakeUpdateApi(firmware={"routerboard": True, "current-firmware": "6.49.19", "upgrade-firmware": "6.49.19"})
    )
    assert same["pending"] is False

    not_a_board = ra.firmware_info(FakeUpdateApi(firmware={"routerboard": False}))
    assert not_a_board["supported"] is False

    assert ra.firmware_info(FakeUpdateApi(firmware_error=True))["supported"] is False


def test_download_waits_for_the_downloaded_status():
    api = FakeUpdateApi(download_statuses=("Downloading", "Downloading", "Downloaded, please reboot router to upgrade it"))
    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        api.poll_status()

    state = ra.download_update(api, sleep=sleep, polls=10, interval=5)
    assert "downloaded" in state["status"].lower()
    assert len(sleeps) >= 2


def test_download_failures():
    api = FakeUpdateApi(download_statuses=("ERROR: not enough space",))
    api.row["status"] = "ERROR: not enough space"
    with pytest.raises(ra.RouterCommandFailed):
        ra.download_update(api, sleep=lambda s: None, polls=3)

    never = FakeUpdateApi(download_statuses=("Downloading",) * 5)
    with pytest.raises(ra.RouterCommandFailed):
        ra.download_update(never, sleep=lambda s: never.poll_status(), polls=2)


def test_auto_firmware_reports_whether_it_worked():
    ok = FakeUpdateApi()
    assert ra.enable_auto_firmware(ok) is True
    assert ("/system/routerboard/settings/set", ("=auto-upgrade=yes",)) in ok.commands
    assert ra.enable_auto_firmware(FakeUpdateApi(auto_upgrade_fails=True)) is False


def test_firmware_upgrade_rules():
    api = FakeUpdateApi()
    info = ra.upgrade_firmware(api)
    assert info["upgrade"] == "6.49.19"
    assert "/system/routerboard/upgrade" in api.names()

    with pytest.raises(InvalidInput):
        ra.upgrade_firmware(FakeUpdateApi(firmware={"routerboard": False}))
    with pytest.raises(InvalidInput):
        ra.upgrade_firmware(
            FakeUpdateApi(firmware={"routerboard": True, "current-firmware": "6.49.19", "upgrade-firmware": "6.49.19"})
        )