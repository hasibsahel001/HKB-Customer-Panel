import re

_NUM_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)")


def leading_number(value):
    """Extract the leading number from values like -62, '-62', '-62@HT20', '87%'."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = _NUM_RE.match(str(value))
    return float(match.group(1)) if match else None


def to_bool(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in ("true", "yes"):
        return True
    if text in ("false", "no"):
        return False
    return None


def pick_wireless_interface(rows):
    """Prefer wlan1, otherwise use the first wireless interface. Never assume it exists."""
    rows = list(rows)
    for row in rows:
        if row.get("name") == "wlan1":
            return row
    return rows[0] if rows else None


def _chains(row):
    """Per-chain signal as shown by Winbox: Tx/Rx signal strength of each chain."""
    chains = []
    for number in range(3):
        tx = leading_number(row.get(f"tx-signal-strength-ch{number}"))
        rx = leading_number(row.get(f"signal-strength-ch{number}"))
        if tx is not None or rx is not None:
            chains.append({"chain": number, "tx_dbm": tx, "rx_dbm": rx})
    return chains


def parse_registration(row):
    signal = leading_number(row.get("signal-strength"))
    snr = leading_number(row.get("signal-to-noise"))
    noise = signal - snr if signal is not None and snr is not None else None
    return {
        "interface": row.get("interface"),
        "mac_address": row.get("mac-address"),
        "radio_name": row.get("radio-name"),
        "signal_dbm": signal,
        "snr_db": snr,
        "noise_floor_dbm": noise,  # derived: signal - snr, only when both exist
        "chains": _chains(row),
        "tx_ccq": leading_number(row.get("tx-ccq")),
        "rx_ccq": leading_number(row.get("rx-ccq")),
        "tx_rate": row.get("tx-rate"),
        "rx_rate": row.get("rx-rate"),
        "uptime": row.get("uptime"),
    }