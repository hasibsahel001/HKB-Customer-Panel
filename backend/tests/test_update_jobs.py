import pytest
from fakes_update import FakeUpdateApi, make_conn_factory

from app.services.update_jobs import Job, JobBusy, JobStore, run_update


def make_job(mode="now", firmware=True, ip="10.229.1.1"):
    return Job(id="j1", user_id=1, ip=ip, tid="1001", mode=mode, firmware=firmware)


def run(api, job, **kw):
    def sleep(seconds):
        api.poll_status()

    run_update(job, make_conn_factory(api, **kw), sleep=sleep)
    return job


def test_update_and_reboot_now_with_firmware():
    api = FakeUpdateApi()
    job = run(api, make_job("now", True))
    assert job.state == "done", job.message
    names = api.names()
    assert names.index("/system/routerboard/settings/set") < names.index("/system/package/update/download")
    assert names.index("/system/package/update/download") < names.index("/system/reboot")
    assert job.result["firmware_auto"] is True
    assert "6.49.19" in job.message
    assert "firmware" in job.message
    assert api.closed is True


def test_update_without_rebooting():
    api = FakeUpdateApi()
    job = run(api, make_job("later", True))
    assert job.state == "done"
    assert "/system/package/update/download" in api.names()
    assert "/system/reboot" not in api.names()
    assert "next time" in job.message


def test_firmware_option_is_skipped_on_devices_without_routerboard():
    api = FakeUpdateApi(firmware={"routerboard": False})
    job = run(api, make_job("now", True))
    assert job.state == "done"
    assert "/system/routerboard/settings/set" not in api.names()
    assert job.result["firmware_auto"] is False


def test_firmware_option_off_does_not_touch_the_firmware_setting():
    api = FakeUpdateApi()
    job = run(api, make_job("now", False))
    assert job.state == "done"
    assert "/system/routerboard/settings/set" not in api.names()


def test_a_failed_auto_upgrade_does_not_stop_the_update():
    api = FakeUpdateApi(auto_upgrade_fails=True)
    job = run(api, make_job("now", True))
    assert job.state == "done"
    assert job.result["firmware_auto"] is False
    assert any("manually" in step["text"] for step in job.steps)


def test_already_up_to_date_downloads_nothing():
    api = FakeUpdateApi(installed="6.49.19", latest="6.49.19", check_status="System is already up to date")
    job = run(api, make_job())
    assert job.state == "done"
    assert "already runs" in job.message
    assert "/system/package/update/download" not in api.names()


def test_major_version_change_is_refused():
    api = FakeUpdateApi(installed="6.49.19", latest="7.20.2")
    job = run(api, make_job())
    assert job.state == "failed"
    assert "major" in job.message
    assert "/system/package/update/download" not in api.names()


def test_router_without_internet_fails_with_its_own_message():
    api = FakeUpdateApi(check_status="ERROR: could not resolve dns name")
    job = run(api, make_job())
    assert job.state == "failed"
    assert "could not resolve" in job.message
    assert "/system/package/update/download" not in api.names()


def test_connection_failure_and_download_crash():
    job = run(FakeUpdateApi(), make_job(), fail_connect=True)
    assert job.state == "failed" and "connect" in job.message

    crashed = run(FakeUpdateApi(fail_download=True), make_job())
    assert crashed.state == "failed"
    assert "Unexpected error" in crashed.message
    assert "/system/reboot" not in FakeUpdateApi().names()


def test_a_failed_download_never_reboots():
    api = FakeUpdateApi(download_statuses=("ERROR: not enough space",))
    job = run(api, make_job("now"))
    assert job.state == "failed"
    assert "/system/reboot" not in api.names()


def test_job_store_allows_one_running_job_per_router():
    store = JobStore()
    first = store.create(user_id=1, ip="10.229.1.1", tid="1", mode="now", firmware=True)
    with pytest.raises(JobBusy):
        store.create(user_id=2, ip="10.229.1.1", tid="1", mode="now", firmware=True)
    other = store.create(user_id=1, ip="10.229.1.2", tid="2", mode="later", firmware=False)
    assert other.id != first.id

    first.finish("done")
    again = store.create(user_id=1, ip="10.229.1.1", tid="1", mode="now", firmware=True)
    assert store.get(again.id) is again
    assert store.get("missing") is None


def test_job_serializes_to_plain_data():
    job = make_job()
    job.step("Connecting")
    job.fail("boom")
    data = job.to_dict()
    assert data["state"] == "failed"
    assert data["message"] == "boom"
    assert data["steps"][0]["text"] == "Connecting"