import time

from app.services.parsing import leading_number, to_bool

MIN_SECONDS = 3
MAX_SECONDS = 30
DEFAULT_SECONDS = 10


def clamp_seconds(value) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return DEFAULT_SECONDS
    return max(MIN_SECONDS, min(MAX_SECONDS, number))


def lan_interface(api) -> str:
    """The interface the DHCP server runs on, else ether1."""
    try:
        for row in api.path("ip", "dhcp-server"):
            if not to_bool(row.get("disabled")) and row.get("interface"):
                return row["interface"]
    except Exception:
        pass
    return "ether1"


def read_rate(api, interface):
    """(upload_bps, download_bps): rx on the LAN side is the customer's upload."""
    try:
        rows = list(api.rawCmd("/interface/monitor-traffic", f"=interface={interface}", "=once="))
    except Exception:
        return None
    if not rows:
        return None
    rx = leading_number(rows[0].get("rx-bits-per-second"))
    tx = leading_number(rows[0].get("tx-bits-per-second"))
    return (
        int(rx) if rx is not None else None,
        int(tx) if tx is not None else None,
    )


def sample_usage(api, seconds, sleep=time.sleep, clock=time.monotonic) -> dict:
    """One-second samples of the total LAN traffic, so the peak of the last moments can be shown."""
    count = clamp_seconds(seconds)
    interface = lan_interface(api)
    start = clock()
    samples = []
    for index in range(count):
        began = clock()
        rate = read_rate(api, interface)
        samples.append(
            {
                "elapsed_ms": round((clock() - start) * 1000),
                "up_bps": rate[0] if rate else None,
                "down_bps": rate[1] if rate else None,
            }
        )
        remaining = 1.0 - (clock() - began)
        if index < count - 1 and remaining > 0:
            sleep(remaining)
    return {"interface": interface, "seconds": count, "samples": samples}