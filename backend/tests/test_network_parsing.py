import pytest

from app.services.network_parsing import (
    build_device,
    ip_sort_key,
    is_active_arp,
    is_very_low_limit,
    parse_duration_seconds,
    parse_lease,
    parse_queue,
    parse_rate,
    parse_rate_pair,
    pick_queue_for_ip,
    queue_matches,
)


@pytest.mark.parametrize(
    "value, expected",
    [
        ("10M", 10_000_000),
        ("512k", 512_000),
        ("1G", 1_000_000_000),
        ("1500000", 1_500_000),
        (2000, 2000),
        ("0", None),
        (None, None),
        ("abc", None),
    ],
)
def test_parse_rate(value, expected):
    assert parse_rate(value) == expected


def test_parse_rate_zero_kept_for_live_rates():
    assert parse_rate("0", zero_is_unlimited=False) == 0


def test_parse_rate_pair():
    assert parse_rate_pair("5M/10M") == (5_000_000, 10_000_000)
    assert parse_rate_pair("0/0") == (None, None)
    assert parse_rate_pair("1200/3400", zero_is_unlimited=False) == (1200, 3400)
    assert parse_rate_pair(None) == (None, None)
    assert parse_rate_pair("bad") == (None, None)


def test_is_very_low_limit():
    assert is_very_low_limit(1000, 1000, 10_000) is True
    assert is_very_low_limit(2_000_000, 2_000_000, 10_000) is False
    assert is_very_low_limit(None, None, 10_000) is False
    assert is_very_low_limit(2_000_000, 1000, 10_000) is True


@pytest.mark.parametrize(
    "value, expected",
    [
        ("1w2d22h26m45s", 858_405),
        ("15m59s", 959),
        ("1h27s", 3_627),
        ("3d10m", 259_800),
        ("45s", 45),
        ("", None),
        (None, None),
        ("soon", None),
        ("12:30:00", None),
    ],
)
def test_parse_duration_seconds(value, expected):
    assert parse_duration_seconds(value) == expected


def test_queue_matches_by_subnet_and_host():
    ips = ["192.168.88.10", "192.168.88.20", "10.0.0.5"]
    assert queue_matches("192.168.88.0/24", ips) == ["192.168.88.10", "192.168.88.20"]
    assert queue_matches("10.0.0.5/32", ips) == ["10.0.0.5"]
    assert queue_matches("10.0.0.5/32,192.168.88.10/32", ips) == ["192.168.88.10", "10.0.0.5"]


def test_queue_matches_ignores_catch_all_and_garbage():
    ips = ["192.168.88.10"]
    assert queue_matches("0.0.0.0/0", ips) == []
    assert queue_matches("ether1", ips) == []
    assert queue_matches("", ips) == []
    assert queue_matches(None, ips) == []


def test_parse_lease():
    lease = parse_lease(
        {
            "address": "192.168.88.10",
            "mac-address": "AA:BB:CC:00:11:22",
            "host-name": "phone",
            "status": "bound",
            "last-seen": "15m59s",
        }
    )
    assert lease["ip"] == "192.168.88.10"
    assert lease["hostname"] == "phone"
    assert lease["last_seen_seconds"] == 959

    empty = parse_lease({"address": "192.168.88.11", "host-name": ""})
    assert empty["hostname"] is None


@pytest.mark.parametrize(
    "row, expected",
    [
        ({"dynamic": True, "complete": True}, True),
        ({"dynamic": True, "complete": False}, False),
        ({"dynamic": False, "complete": True}, False),
        ({"dynamic": True, "complete": True, "disabled": True}, False),
        ({"dynamic": True, "complete": True, "invalid": True}, False),
        ({"dynamic": "true", "complete": "true"}, True),
        ({}, False),
    ],
)
def test_is_active_arp(row, expected):
    assert is_active_arp(row) is expected


def _queue(name, target, disabled=False, up=0, down=0):
    row = {
        "name": name,
        "target": target,
        "parent": "none",
        "disabled": disabled,
        "max-limit": "2M/2M",
        "rate": f"{up}/{down}",
    }
    return parse_queue(row, 10_000)


def test_parse_queue():
    q = parse_queue(
        {"name": "q1", "target": "10.0.0.5/32", "max-limit": "1000/1000", "rate": "1200/3400"},
        10_000,
    )
    assert q["max_limit_upload_bps"] == 1000
    assert q["current_upload_bps"] == 1200
    assert q["current_download_bps"] == 3400
    assert q["very_low_limit"] is True


def test_pick_queue_prefers_most_specific_and_skips_disabled():
    queues = [
        _queue("wide", "10.0.0.0/24"),
        _queue("host", "10.0.0.5/32"),
        _queue("off", "10.0.0.6/32", disabled=True),
    ]
    assert pick_queue_for_ip(queues, "10.0.0.5")["name"] == "host"
    assert pick_queue_for_ip(queues, "10.0.0.6")["name"] == "wide"
    assert pick_queue_for_ip(queues, "172.16.0.1") is None


def test_build_device_with_and_without_queue():
    queues = [_queue("host", "10.0.0.5/32", up=1200, down=3400)]
    lease_by_ip = {"10.0.0.5": {"hostname": "phone", "status": "bound"}}

    measured = build_device(
        {"address": "10.0.0.5", "mac-address": "AA:BB:CC:00:11:22", "interface": "ether1"},
        lease_by_ip,
        queues,
    )
    assert measured["hostname"] == "phone"
    assert measured["usage"]["method"] == "simple_queue_rate"
    assert measured["usage"]["upload_bps"] == 1200
    assert measured["usage"]["download_bps"] == 3400

    unmeasured = build_device(
        {"address": "10.0.0.9", "mac-address": "AA:BB:CC:00:11:33", "interface": "ether1"},
        lease_by_ip,
        queues,
    )
    assert unmeasured["hostname"] is None
    assert unmeasured["usage"]["method"] is None
    assert unmeasured["usage"]["upload_bps"] is None


def test_ip_sort_key_is_numeric():
    ips = ["192.168.88.100", "192.168.88.9", "bad"]
    assert sorted(ips, key=ip_sort_key) == ["192.168.88.9", "192.168.88.100", "bad"]