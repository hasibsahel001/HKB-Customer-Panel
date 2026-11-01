from app.core.config import settings
from app.services.filtering import (
    HIDDEN_FINDING_CODES,
    drop_infrastructure_devices,
    hide_findings,
    overall_of,
)


def finding(code, severity):
    return {"code": code, "severity": severity}


def test_the_unwanted_findings_are_in_the_hidden_set():
    assert {"queue_very_low_limit", "queue_overlap", "dhcp_ip_conflict"} <= HIDDEN_FINDING_CODES


def test_hidden_findings_are_removed_and_the_overall_status_is_recomputed():
    diagnostics = {
        "overall": "serious",
        "count": 4,
        "findings": [
            finding("queue_very_low_limit", "serious"),
            finding("queue_overlap", "unknown"),
            finding("dhcp_ip_conflict", "warning"),
            finding("cpu_high", "warning"),
        ],
    }
    result = hide_findings(diagnostics)
    assert [f["code"] for f in result["findings"]] == ["cpu_high"]
    assert result["count"] == 1
    assert result["overall"] == "warning"


def test_only_hidden_findings_leave_a_normal_status():
    diagnostics = {"overall": "serious", "count": 1, "findings": [finding("queue_very_low_limit", "serious")]}
    assert hide_findings(diagnostics)["overall"] == "normal"


def test_nothing_changes_when_no_finding_is_hidden():
    diagnostics = {"overall": "warning", "count": 1, "findings": [finding("cpu_high", "warning")]}
    assert hide_findings(diagnostics) is diagnostics
    assert diagnostics["count"] == 1


def test_bad_input_is_returned_as_is():
    assert hide_findings(None) is None
    assert hide_findings({"findings": None}) == {"findings": None}


def test_overall_ignores_informational_findings():
    assert overall_of([finding("a", "normal")]) == "normal"
    assert overall_of([finding("a", "normal"), finding("b", "unknown")]) == "unknown"
    assert overall_of([finding("a", "serious"), finding("b", "critical")]) == "critical"
    assert overall_of([]) == "normal"


def test_the_customers_access_point_is_not_a_device(monkeypatch):
    monkeypatch.setattr(settings, "ap_probe_peers", ["10.10.10.2", "192.168.0.1", "not-an-ip"])
    report = {
        "sections": {
            "devices": {
                "ok": True,
                "data": {
                    "count": 4,
                    "devices": [
                        {"ip": "10.10.10.2"},
                        {"ip": "10.10.10.7"},
                        {"ip": "192.168.0.1"},
                        {"ip": "192.168.1.1"},
                    ],
                },
            }
        }
    }
    drop_infrastructure_devices(report)
    data = report["sections"]["devices"]["data"]
    assert [d["ip"] for d in data["devices"]] == ["10.10.10.7", "192.168.1.1"]
    assert data["count"] == 2


def test_a_missing_or_failed_devices_section_is_fine():
    assert drop_infrastructure_devices({"sections": {}}) == {"sections": {}}
    failed = {"sections": {"devices": {"ok": False, "data": None}}}
    assert drop_infrastructure_devices(failed) is failed
    assert drop_infrastructure_devices({}) == {}