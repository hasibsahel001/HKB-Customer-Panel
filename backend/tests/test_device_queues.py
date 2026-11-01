from app.services.device_queues import describe_device_queue
from app.services.network_parsing import parse_queue


def make(name, target, limit="2M/2M", disabled=False):
    return parse_queue(
        {
            "name": name,
            "target": target,
            "parent": "none",
            "disabled": disabled,
            "max-limit": limit,
            "rate": "0/0",
        },
        10_000,
    )


def test_own_queue_wins_over_shared_ones():
    queues = [
        make("free", "10.0.0.0/24"),
        make("host", "10.0.0.5/32", "7M/7M"),
        make("others", "10.0.0.0/24"),
    ]
    result = describe_device_queue(queues, "10.0.0.5")
    assert result["scope"] == "own"
    assert result["names"] == ["host", "free", "others"]
    assert result["limit_upload_bps"] == 7_000_000
    assert result["ambiguous"] is False


def test_tied_shared_queues_are_ambiguous():
    queues = [make("free", "10.0.0.0/24"), make("others", "10.0.0.0/24")]
    result = describe_device_queue(queues, "10.0.0.9")
    assert result["scope"] == "shared"
    assert result["names"] == ["free", "others"]
    assert result["ambiguous"] is True
    assert result["limit_upload_bps"] is None


def test_single_shared_queue_keeps_its_limit():
    result = describe_device_queue([make("lan", "10.0.0.0/24", "3M/4M")], "10.0.0.9")
    assert result["scope"] == "shared"
    assert result["ambiguous"] is False
    assert result["limit_upload_bps"] == 3_000_000
    assert result["limit_download_bps"] == 4_000_000


def test_no_queue_for_other_addresses():
    result = describe_device_queue([make("lan", "10.0.0.0/24")], "172.16.0.1")
    assert result["scope"] == "none"
    assert result["names"] == []


def test_disabled_and_catch_all_queues_are_ignored():
    queues = [make("off", "10.0.0.5/32", disabled=True), make("all", "0.0.0.0/0")]
    assert describe_device_queue(queues, "10.0.0.5")["scope"] == "none"


def test_multi_target_queue_matches_each_host():
    queues = [make("pair", "10.0.0.5/32,10.0.0.6/32", "1M/1M")]
    assert describe_device_queue(queues, "10.0.0.6")["scope"] == "own"


def test_invalid_address_is_unknown():
    assert describe_device_queue([], "not-an-ip")["scope"] == "unknown"