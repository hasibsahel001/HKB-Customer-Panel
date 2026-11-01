from app.services.diagnostics import diagnose


def ok(data):
    return {"ok": True, "data": data, "error": None}


def blocking_queue(name="block-h"):
    return {
        "name": name, "target": "10.10.10.74/32", "disabled": False,
        "max_limit_upload_bps": 1_000_000, "max_limit_download_bps": 1_000_000,
        "current_upload_bps": 999_000, "current_download_bps": 999_000,
        "very_low_limit": False,
    }


def real_queue():
    return {
        "name": "package-10m", "target": "10.10.10.75/32", "disabled": False,
        "max_limit_upload_bps": 10_000_000, "max_limit_download_bps": 10_000_000,
        "current_upload_bps": 9_800_000, "current_download_bps": 1_000_000,
        "very_low_limit": False,
    }


def test_a_blocking_queue_never_produces_near_limit_or_very_low_findings():
    snapshot = {"sections": {"queues": ok({"queues": [blocking_queue()]})}}
    codes = {f["code"] for f in diagnose(snapshot)["findings"]}
    assert "queue_near_limit" not in codes
    assert "queue_very_low_limit" not in codes


def test_a_blocking_queue_name_is_matched_case_insensitively():
    snapshot = {"sections": {"queues": ok({"queues": [blocking_queue("Block-Phone")]})}}
    codes = {f["code"] for f in diagnose(snapshot)["findings"]}
    assert "queue_near_limit" not in codes


def test_a_real_package_queue_still_warns_near_its_limit():
    snapshot = {"sections": {"queues": ok({"queues": [real_queue()]})}}
    codes = {f["code"] for f in diagnose(snapshot)["findings"]}
    assert "queue_near_limit" in codes


def test_a_blocking_queue_does_not_count_toward_overlap_either():
    snapshot = {"sections": {"queues": ok({"queues": [blocking_queue(), real_queue()]})}}
    codes = {f["code"] for f in diagnose(snapshot)["findings"]}
    assert "queue_overlap" not in codes  # only one non-blocking queue remains