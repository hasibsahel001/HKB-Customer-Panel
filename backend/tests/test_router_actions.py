import pytest
from librouteros import exceptions as ros_exc

from app.core.errors import InvalidInput
from app.services import router_actions as ra


class FakePath:
    def __init__(self, rows):
        self.rows = rows

    def __iter__(self):
        return iter(list(self.rows))

    def add(self, **kw):
        new_id = f"*{len(self.rows) + 10:X}"
        self.rows.append({".id": new_id, **kw})
        return new_id

    def update(self, **kw):
        row = next(r for r in self.rows if r[".id"] == kw[".id"])
        row.update({k: v for k, v in kw.items() if k != ".id"})

    def remove(self, *ids):
        self.rows[:] = [r for r in self.rows if r[".id"] not in ids]


class FakeApi:
    def __init__(self, rows, reboot_error=None):
        self.queue = FakePath(rows)
        self.reboot_error = reboot_error

    def path(self, *parts):
        assert parts == ("queue", "simple")
        return self.queue

    def rawCmd(self, cmd, *words):
        assert cmd == "/system/reboot"
        if self.reboot_error:
            raise self.reboot_error
        return iter([])


def sample_rows():
    return [
        {".id": "*1", "name": "Roya's Phone", "target": "10.10.10.74/32,10.10.10.72/32",
         "max-limit": "7000000/7000000", "disabled": "false", "parent": "none"},
        {".id": "*2", "name": "others", "target": "10.20.0.0/24", "max-limit": "2M/3M",
         "disabled": "true", "parent": "none", "comment": "old"},
    ]


@pytest.mark.parametrize(
    "text, expected",
    [("10M", "10M"), ("10m", "10M"), ("512K", "512k"), ("1.5M", "1.5M"), ("1g", "1G"), ("0", "0"), ("0M", "0"), (" 2M ", "2M")],
)
def test_normalize_rate(text, expected):
    assert ra.normalize_rate(text) == expected


@pytest.mark.parametrize("text", ["", "fast", "10MB", "-5M", "1e3", "M"])
def test_normalize_rate_rejects(text):
    with pytest.raises(InvalidInput):
        ra.normalize_rate(text)


def test_bps_to_text():
    assert ra.bps_to_text(10_000_000) == "10M"
    assert ra.bps_to_text(512_000) == "512k"
    assert ra.bps_to_text(1_234) == "1234"
    assert ra.bps_to_text(None) == "0"


def test_targets():
    assert ra.normalize_target("10.10.10.5") == "10.10.10.5/32"
    assert ra.normalize_target("10.10.10.0/24") == "10.10.10.0/24"
    assert ra.normalize_targets(["10.0.0.1", "10.0.0.1/32", "10.0.0.2"]) == ["10.0.0.1/32", "10.0.0.2/32"]
    for bad in ["10.10.10.5/24", "0.0.0.0/0", "::1", "abc", "", "300.1.1.1"]:
        with pytest.raises(InvalidInput):
            ra.normalize_target(bad)
    with pytest.raises(InvalidInput):
        ra.normalize_targets([])
    with pytest.raises(InvalidInput):
        ra.normalize_targets([f"10.0.{i // 250}.{i % 250 + 1}" for i in range(ra.MAX_TARGETS + 1)])


def test_names_and_ids():
    assert ra.validate_name(" Roya's Phone ") == "Roya's Phone"
    for bad in ["", "x" * 65, "bad\nname"]:
        with pytest.raises(InvalidInput):
            ra.validate_name(bad)
    assert ra.validate_ids(["*1", "*A2"]) == ["*1", "*A2"]
    for bad in [[], ["1"], ["*1; /system reboot"], ["*"]]:
        with pytest.raises(InvalidInput):
            ra.validate_ids(bad)


def test_list_shows_every_queue_and_marks_the_customers():
    api = FakeApi(sample_rows())
    queues = ra.list_all_queues(api, ["10.10.10.74"])
    assert [q["name"] for q in queues] == ["Roya's Phone", "others"]
    first, second = queues
    assert first["targets"] == ["10.10.10.74/32", "10.10.10.72/32"]
    assert first["max_up"] == "7M" and first["max_up_bps"] == 7_000_000
    assert first["matches_customer"] is True
    assert second["matches_customer"] is False
    assert second["disabled"] is True
    assert second["max_down"] == "3M"
    assert second["comment"] == "old"


def test_create_update_and_delete():
    api = FakeApi(sample_rows())
    new_id = ra.save_queue(
        api, queue_id=None, name="New", targets=["10.1.1.1", "10.1.1.2"], max_up="10M", max_down="5M", disabled=False
    )
    created = next(r for r in api.queue.rows if r[".id"] == new_id)
    assert created["target"] == "10.1.1.1/32,10.1.1.2/32"
    assert created["max-limit"] == "10M/5M"
    assert created["disabled"] == "no"

    ra.save_queue(
        api, queue_id="*1", name="Renamed", targets=["10.10.10.74", "10.10.10.99"], max_up="8M", max_down="8M", disabled=True
    )
    updated = next(r for r in api.queue.rows if r[".id"] == "*1")
    assert updated["name"] == "Renamed"
    assert updated["target"] == "10.10.10.74/32,10.10.10.99/32"
    assert updated["disabled"] == "yes"

    assert ra.delete_queues(api, ["*2"]) == 1
    assert [r[".id"] for r in api.queue.rows] == ["*1", new_id]
    assert ra.delete_all_queues(api) == 2
    assert api.queue.rows == []
    assert ra.delete_all_queues(api) == 0


def test_update_of_a_missing_queue_is_rejected():
    api = FakeApi(sample_rows())
    with pytest.raises(InvalidInput):
        ra.save_queue(api, queue_id="*9", name="x", targets=["10.0.0.1"], max_up="1M", max_down="1M", disabled=False)
    with pytest.raises(InvalidInput):
        ra.save_queue(api, queue_id="bad", name="x", targets=["10.0.0.1"], max_up="1M", max_down="1M", disabled=False)


def test_invalid_input_never_reaches_the_router():
    api = FakeApi(sample_rows())
    before = list(api.queue.rows)
    with pytest.raises(InvalidInput):
        ra.save_queue(api, queue_id=None, name="x", targets=["0.0.0.0/0"], max_up="1M", max_down="1M", disabled=False)
    assert api.queue.rows == before


def test_reboot_treats_a_dropped_connection_as_sent():
    ra.send_reboot(FakeApi([], reboot_error=ros_exc.FatalError("connection terminated")))
    ra.send_reboot(FakeApi([], reboot_error=OSError("reset")))
    ra.send_reboot(FakeApi([]))


def test_reboot_does_not_hide_other_errors():
    with pytest.raises(RuntimeError):
        ra.send_reboot(FakeApi([], reboot_error=RuntimeError("boom")))