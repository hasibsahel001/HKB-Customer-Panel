import ipaddress
import re

from app.services.parsing import to_bool

_RATE_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([kKmMgG]?)\s*$")
_MULTIPLIER = {"": 1, "k": 1_000, "m": 1_000_000, "g": 1_000_000_000}

_DURATION_RE = re.compile(r"(\d+)([wdhms])")
_UNIT_SECONDS = {"w": 604_800, "d": 86_400, "h": 3_600, "m": 60, "s": 1}


def parse_rate(value, zero_is_unlimited=True):
    """Convert '10M', '512k', '1500000' to bits per second.

    For limits, 0 means unlimited and is returned as None.
    For live rates, pass zero_is_unlimited=False so 0 stays 0.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = int(value)
    else:
        match = _RATE_RE.match(str(value))
        if not match:
            return None
        number = int(float(match.group(1)) * _MULTIPLIER[match.group(2).lower()])
    if number == 0 and zero_is_unlimited:
        return None
    return number


def parse_rate_pair(value, zero_is_unlimited=True):
    """Parse 'upload/download' into (upload_bps, download_bps)."""
    if not value:
        return (None, None)
    parts = str(value).split("/")
    if len(parts) != 2:
        return (None, None)
    return (
        parse_rate(parts[0], zero_is_unlimited),
        parse_rate(parts[1], zero_is_unlimited),
    )


def is_very_low_limit(upload_bps, download_bps, threshold_bps):
    """True when any configured limit is at or below the threshold."""
    limits = [v for v in (upload_bps, download_bps) if v is not None]
    return any(v <= threshold_bps for v in limits)


def parse_duration_seconds(value):
    """Convert RouterOS durations like '1w2d22h26m45s' to seconds. Unknown formats return None."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    matches = _DURATION_RE.findall(text)
    if not matches:
        return None
    if "".join(number + unit for number, unit in matches) != text:
        return None
    return sum(int(number) * _UNIT_SECONDS[unit] for number, unit in matches)


def parse_targets(value):
    networks = []
    for part in str(value or "").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            networks.append(ipaddress.ip_network(part, strict=False))
        except ValueError:
            continue  # interface names or garbage are ignored
    return networks


def queue_matches(target, ips):
    """Return the IPs covered by a queue target.

    Catch-all targets (prefix length 0) are not evidence of a customer relation.
    """
    networks = [n for n in parse_targets(target) if n.prefixlen > 0]
    matched = []
    for raw in ips:
        try:
            addr = ipaddress.ip_address(raw)
        except (ValueError, TypeError):
            continue
        if any(addr in net for net in networks if net.version == addr.version):
            matched.append(str(addr))
    return matched


def ip_sort_key(ip):
    try:
        return (0, int(ipaddress.ip_address(ip)))
    except (ValueError, TypeError):
        return (1, 0)


def parse_lease(row):
    """Lease data is used only to look up hostnames and lease status for ARP devices."""
    return {
        "ip": row.get("active-address") or row.get("address"),
        "mac_address": row.get("active-mac-address") or row.get("mac-address"),
        "hostname": row.get("host-name") or None,
        "status": row.get("status"),
        "server": row.get("server"),
        "expires_after": row.get("expires-after"),
        "last_seen": row.get("last-seen"),
        "last_seen_seconds": parse_duration_seconds(row.get("last-seen")),
        "dynamic": to_bool(row.get("dynamic")),
        "disabled": to_bool(row.get("disabled")),
    }


def is_active_arp(row):
    """Equivalent of the D and C flags: dynamic and complete, not disabled or invalid."""
    return (
        to_bool(row.get("dynamic")) is True
        and to_bool(row.get("complete")) is True
        and not to_bool(row.get("disabled"))
        and not to_bool(row.get("invalid"))
    )


def parse_queue(row, very_low_threshold_bps):
    limit_up, limit_down = parse_rate_pair(row.get("max-limit"))
    rate_up, rate_down = parse_rate_pair(row.get("rate"), zero_is_unlimited=False)
    return {
        "name": row.get("name"),
        "target": row.get("target"),
        "parent": row.get("parent"),
        "disabled": to_bool(row.get("disabled")),
        "max_limit_upload_bps": limit_up,
        "max_limit_download_bps": limit_down,
        "current_upload_bps": rate_up,
        "current_download_bps": rate_down,
        "very_low_limit": is_very_low_limit(limit_up, limit_down, very_low_threshold_bps),
    }


def _best_prefix(target, ip):
    try:
        addr = ipaddress.ip_address(ip)
    except (ValueError, TypeError):
        return -1
    best = -1
    for net in parse_targets(target):
        if net.prefixlen > 0 and net.version == addr.version and addr in net:
            best = max(best, net.prefixlen)
    return best


def pick_queue_for_ip(queues, ip):
    """Pick the most specific enabled queue whose target covers the IP."""
    best_queue = None
    best_prefix = -1
    for queue in queues:
        if queue.get("disabled"):
            continue
        prefix = _best_prefix(queue.get("target"), ip)
        if prefix > best_prefix:
            best_queue, best_prefix = queue, prefix
    return best_queue


def build_device(arp_row, lease_by_ip, queues):
    ip = arp_row.get("address")
    lease = lease_by_ip.get(ip) or {}
    queue = pick_queue_for_ip(queues, ip)
    if queue is not None:
        usage = {
            "method": "simple_queue_rate",
            "queue": queue["name"],
            "upload_bps": queue["current_upload_bps"],
            "download_bps": queue["current_download_bps"],
        }
    else:
        usage = {"method": None, "queue": None, "upload_bps": None, "download_bps": None}
    return {
        "ip": ip,
        "mac_address": arp_row.get("mac-address"),
        "interface": arp_row.get("interface"),
        "hostname": lease.get("hostname"),
        "lease_status": lease.get("status"),
        "limit_upload_bps": queue["max_limit_upload_bps"] if queue else None,
        "limit_download_bps": queue["max_limit_download_bps"] if queue else None,
        "usage": usage,
    }