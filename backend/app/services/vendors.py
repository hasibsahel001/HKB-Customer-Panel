import re
from pathlib import Path

# A few MikroTik prefixes only. Add more (TP-Link, Tenda, ...) in backend/oui.csv.
_BUILTIN = {
    "00:0C:42": "MikroTik",
    "4C:5E:0C": "MikroTik",
    "64:D1:54": "MikroTik",
    "6C:3B:6B": "MikroTik",
    "B8:69:F4": "MikroTik",
    "CC:2D:E0": "MikroTik",
    "D4:CA:6D": "MikroTik",
    "E4:8D:8C": "MikroTik",
}

OUI_FILE = Path(__file__).resolve().parents[2] / "oui.csv"


def normalize_prefix(value):
    digits = re.sub(r"[^0-9A-Fa-f]", "", value or "").upper()
    if len(digits) < 6:
        return None
    return ":".join(digits[i : i + 2] for i in (0, 2, 4))


def load_table(path: Path = OUI_FILE) -> dict:
    table = dict(_BUILTIN)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return table
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        prefix, _, vendor = line.partition(",")
        key = normalize_prefix(prefix)
        if key and vendor.strip():
            table[key] = vendor.strip()
    return table


_TABLE = load_table()


def lookup_vendor(mac, table=None):
    key = normalize_prefix(mac)
    if key is None:
        return None
    return (table if table is not None else _TABLE).get(key)