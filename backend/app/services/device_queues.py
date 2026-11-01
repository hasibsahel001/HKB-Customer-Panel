import ipaddress

from app.services.network_parsing import parse_targets

UNKNOWN_QUEUE = {
    "scope": "unknown",
    "names": [],
    "limit_upload_bps": None,
    "limit_download_bps": None,
    "ambiguous": False,
}


def _covering_prefix(target, addr):
    """Longest prefix among the targets that cover the address, or -1."""
    best = -1
    for net in parse_targets(target):
        if net.prefixlen > 0 and net.version == addr.version and addr in net:
            best = max(best, net.prefixlen)
    return best


def describe_device_queue(queues, ip):
    """Describe which simple queues apply to one device, judged only by target addresses.

    scope: 'own' (a queue targets this host), 'shared' (only wider subnet queues),
    'none' (no queue), 'unknown' (the address could not be parsed).
    When several queues tie for the most specific match, the effective limit depends on
    queue order and schedules, which are not read, so the limit is left out (ambiguous).
    """
    try:
        addr = ipaddress.ip_address(ip)
    except (ValueError, TypeError):
        return dict(UNKNOWN_QUEUE)

    matches = []
    for queue in queues:
        if queue.get("disabled"):
            continue
        prefix = _covering_prefix(queue.get("target"), addr)
        if prefix > 0:
            matches.append((prefix, queue))

    if not matches:
        return {
            "scope": "none",
            "names": [],
            "limit_upload_bps": None,
            "limit_download_bps": None,
            "ambiguous": False,
        }

    matches.sort(key=lambda item: -item[0])  # stable: router order is kept within a tie
    best_prefix, best = matches[0]
    ambiguous = sum(1 for prefix, _ in matches if prefix == best_prefix) > 1
    return {
        "scope": "own" if best_prefix == addr.max_prefixlen else "shared",
        "names": [q.get("name") or "unnamed" for _, q in matches],
        "limit_upload_bps": None if ambiguous else best.get("max_limit_upload_bps"),
        "limit_download_bps": None if ambiguous else best.get("max_limit_download_bps"),
        "ambiguous": ambiguous,
    }