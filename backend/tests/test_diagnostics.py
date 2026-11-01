import pytest

from app.core.config import settings
from app.services.diagnostics import diagnose

_RANK = ["unknown", "normal", "warning", "serious", "critical"]


@pytest.fixture(autouse=True)
def thresholds(monkeypatch):
    monkeypatch.setattr(settings, "signal_normal_dbm", -60.0)
    monkeypatch.setattr(settings, "signal_warning_dbm", -70.0)
    monkeypatch.setattr(settings, "signal_serious_dbm", -80.0)
    monkeypatch.setattr(settings, "ccq_normal_percent", 80.0)
    monkeypatch.setattr(settings, "ccq_serious_percent", 60.0)
    monkeypatch.setattr(settings, "cpu_warning_percent", 80.0)
    monkeypatch.setattr(settings, "cpu_serious_percent", 95.0)
    monkeypatch.setattr(settings, "ram_warning_percent", 85.0)
    monkeypatch.setattr(settings, "ram_serious_percent", 95.0)
    monkeypatch.setattr(settings, "queue_usage_warning_percent", 90.0)
    monkeypatch.setattr(settings, "queue_very_low_limit_bps", 10_000)


def ok(data):
    return {"ok": True, "data": data, "error": None, "error_type": None, "error_detail": None}


def fail(detail):
    return {
        "ok": False,
        "data": None,
        "error": "unavailable",
        "error_type": "RuntimeError",
        "error_detail": detail,
    }


def snap(**sections):
    return {"sections": sections}


def by_code(result):
    return {f["code"]: f for f in result["findings"]}


def wireless(signal="normal", ccq="normal", registered=True, running=True):
    overall = max([signal, ccq], key=_RANK.index)
    return {
        "interface": "wlan1",
        "running": running,
        "disabled": False,
        "ssid": "HB",
        "frequency": 5610,
        "registration_count": 1 if registered else 0,
        "registration": {
            "signal_dbm": -55,
            "snr_db": 40,
            "noise_floor_dbm": -95,
            "tx_ccq": 70,
            "rx_ccq": 90,
            "tx_rate": "28.8Mbps",
            "rx_rate": "57.7Mbps",
        },
        "ccq_used": 70,
        "ccq_source": "tx",
        "analysis": {"signal": signal, "ccq": ccq, "overall": overall},
    }


def ping(gateway_reachable=True, internet_reachable=True, gateway_status="normal", target_status="normal"):
    def entry(host, reachable, status):
        return {
            "host": host,
            "summary": {
                "sent": 4,
                "received": 4 if reachable else 0,
                "loss_percent": 0,
                "avg_ms": 20.0,
                "max_ms": 30.0,
                "reachable": reachable,
            },
            "reachable": reachable,
            "status": status,
            "error": None,
        }

    return {
        "layers": {
            "router_connected": True,
            "pppoe_running": True,
            "gateway_reachable": gateway_reachable,
            "internet_reachable": internet_reachable,
        },
        "gateway": entry("10.0.0.1", gateway_reachable, gateway_status),
        "targets": [entry("8.8.8.8", internet_reachable, target_status)],
    }


def queue(name, target="10.10.10.0/24", up=2_000_000, down=2_000_000, cur_up=0, cur_down=0, very_low=False):
    return {
        "name": name,
        "target": target,
        "parent": "none",
        "disabled": False,
        "max_limit_upload_bps": up,
        "max_limit_download_bps": down,
        "current_upload_bps": cur_up,
        "current_download_bps": cur_down,
        "very_low_limit": very_low,
        "matched_ips": ["10.10.10.5"],
    }


def queues(*items):
    return {
        "total_count": len(items),
        "matched_count": len(items),
        "unmatched_count": 0,
        "skipped_rows": 0,
        "skipped_reasons": [],
        "queues": list(items),
    }


def test_no_data_means_normal_with_no_findings():
    result = diagnose(snap())
    assert result["overall"] == "normal"
    assert result["findings"] == []


def test_ccq_low_with_good_signal():
    result = diagnose(snap(wireless=ok(wireless(signal="normal", ccq="warning"))))
    findings = by_code(result)
    assert "wireless_ccq_low_with_good_signal" in findings
    assert findings["wireless_ccq_low_with_good_signal"]["severity"] == "warning"
    assert result["overall"] == "warning"


def test_signal_and_ccq_both_bad():
    result = diagnose(snap(wireless=ok(wireless(signal="serious", ccq="warning"))))
    findings = by_code(result)
    assert findings["wireless_link_quality_low"]["severity"] == "serious"


def test_signal_only_weak():
    result = diagnose(snap(wireless=ok(wireless(signal="warning", ccq="normal"))))
    assert "wireless_signal_weak" in by_code(result)


def test_wireless_not_registered_is_critical():
    result = diagnose(snap(wireless=ok(wireless(registered=False))))
    assert by_code(result)["wireless_not_registered"]["severity"] == "critical"
    assert result["overall"] == "critical"


def test_wireless_interface_down():
    result = diagnose(snap(wireless=ok(wireless(running=False))))
    assert by_code(result)["wireless_interface_down"]["severity"] == "critical"


def test_pppoe_down_and_mismatch():
    pppoe = {"name": "p", "running": False, "status": "disconnected", "matches_panel_ip": False,
             "local_address": "100.1.1.1", "underlying_interface": "wlan1"}
    result = diagnose(snap(pppoe=ok(pppoe)))
    findings = by_code(result)
    assert findings["pppoe_down"]["severity"] == "critical"
    assert findings["pppoe_ip_mismatch"]["severity"] == "serious"


def test_pppoe_connected_is_clean():
    pppoe = {"name": "p", "running": True, "status": "connected", "matches_panel_ip": True,
             "local_address": "100.1.1.1", "underlying_interface": "wlan1"}
    assert diagnose(snap(pppoe=ok(pppoe)))["findings"] == []


def test_gateway_unreachable():
    result = diagnose(snap(ping=ok(ping(gateway_reachable=False, internet_reachable=False))))
    findings = by_code(result)
    assert findings["gateway_unreachable"]["severity"] == "critical"
    assert "internet_unreachable" not in findings


def test_internet_unreachable_with_gateway_ok():
    result = diagnose(snap(ping=ok(ping(gateway_reachable=True, internet_reachable=False))))
    assert by_code(result)["internet_unreachable"]["severity"] == "serious"


def test_internet_ping_degraded():
    result = diagnose(snap(ping=ok(ping(target_status="warning"))))
    assert by_code(result)["internet_ping_degraded"]["severity"] == "warning"


def test_queue_very_low_limit_and_overlap():
    items = [queue("a", very_low=True, up=1000, down=1000), queue("b")]
    result = diagnose(snap(queues=ok(queues(*items))))
    findings = by_code(result)
    assert findings["queue_very_low_limit"]["severity"] == "serious"
    assert findings["queue_overlap"]["severity"] == "unknown"


def test_queue_near_limit():
    result = diagnose(snap(queues=ok(queues(queue("a", cur_down=1_900_000)))))
    finding = by_code(result)["queue_near_limit"]
    assert finding["evidence"]["direction"] == "download"
    assert finding["evidence"]["usage_percent"] == 95.0


def test_cpu_and_ram_levels():
    high = diagnose(snap(resource=ok({"cpu_load": 97, "ram_used_percent": 88.0})))
    findings = by_code(high)
    assert findings["cpu_high"]["severity"] == "serious"
    assert findings["ram_high"]["severity"] == "warning"

    normal = diagnose(snap(resource=ok({"cpu_load": 20, "ram_used_percent": 40.0})))
    assert normal["findings"] == []


def test_known_and_unknown_unavailable_reasons():
    result = diagnose(
        snap(dhcp=fail("no dhcp server"), queues=fail("something odd"))
    )
    findings = by_code(result)
    assert findings["dhcp_server_not_found"]["severity"] == "warning"
    assert findings["section_unavailable"]["severity"] == "unknown"
    assert findings["section_unavailable"]["evidence"]["section"] == "queues"


def test_only_unknown_findings_give_unknown_overall():
    result = diagnose(snap(queues=fail("x")))
    assert result["overall"] == "unknown"


def test_critical_wins_overall():
    result = diagnose(
        snap(
            wireless=ok(wireless(registered=False)),
            queues=fail("x"),
        )
    )
    assert result["overall"] == "critical"
    assert result["findings"][0]["severity"] == "critical"


def test_no_devices_finding():
    devices = {"interfaces": ["ether1"], "count": 0, "total_traffic": None, "devices": []}
    ether1 = {"running": True, "disabled": False}
    result = diagnose(snap(devices=ok(devices), ether1=ok(ether1)))
    assert "no_devices_detected" in by_code(result)

    down = diagnose(snap(devices=ok(devices), ether1=ok({"running": False, "disabled": False})))
    assert "no_devices_detected" not in by_code(down)
    assert "ether1_down" in by_code(down)