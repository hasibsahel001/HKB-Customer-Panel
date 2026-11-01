"""Which devices are online behind a customer router.

Shared by the full check (snapshot) and the fast background refresh (live_devices).

Why this is broader than "ARP entries flagged D and C on the DHCP interface":
  * The ARP interface is not always the DHCP server interface (bridges, VLANs, a DHCP server
    that lives on another device), so devices were silently dropped. Every interface except the
    uplink (the PPPoE client and the interface it runs over) is now treated as the customer LAN.
  * Static-IP devices have non-dynamic ARP entries and were never counted.
  * A device that has just received a DHCP lease can be missing from ARP for a moment.
"""

import logging

from app.services.device_queues import UNKNOWN_QUEUE, describe_device_queue
from app.services.network_parsing import ip_sort_key
from app.services.parsing import leading_number, to_bool

log = logging.getLogger("hkb.devices")

# A bound lease seen this recently counts as online even when ARP has not caught up yet.
LEASE_ACTIVE_SECONDS = 120


def lan_exclusions(api) -> set:
    """Interface names that are the uplink, not the customer's LAN (PPPoE client and its carrier)."""
    names: set = set()
    try:
        for row in list(api.path("interface", "pppoe-client")):
            for key in ("name", "interface"):
                if row.get(key):
                    names.add(row[key])
    except Exception as exc:
        log.info("pppoe clients unavailable for LAN detection: %s", type(exc).__name__)
    return names


def arp_is_present(row) -> bool:
    """A usable ARP entry: not disabled or invalid, and resolved to a MAC address."""
    if to_bool(row.get("disabled")) or to_bool(row.get("invalid")):
        return False
    complete = to_bool(row.get("complete"))
    if to_bool(row.get("dynamic")) is True:
        return complete is True
    return complete is not False  # static entries


def _device(ip, mac, interface, lease, source, queues) -> dict:
    queue = describe_device_queue(queues, ip) if queues is not None else dict(UNKNOWN_QUEUE)
    return {
        "ip": ip,
        "mac_address": mac,
        "interface": interface,
        "hostname": lease.get("hostname"),
        "lease_status": lease.get("status"),
        "source": source,
        "queue_scope": queue["scope"],
        "queue_names": queue["names"],
        "queue_limit_upload_bps": queue["limit_upload_bps"],
        "queue_limit_download_bps": queue["limit_download_bps"],
        "queue_ambiguous": queue["ambiguous"],
    }


def collect_devices(
    api,
    *,
    queues,
    lease_by_ip,
    lan_interfaces,
    server_interfaces=None,
    exclude=None,
) -> list:
    """The online devices, sorted by IP.

    exclude: uplink interface names. When known, every other ARP interface counts as LAN.
    lan_interfaces: used only when exclude is empty (the uplink could not be detected).
    """
    exclude = exclude or set()
    server_interfaces = server_interfaces or {}
    devices: list = []
    seen: set = set()

    for row in list(api.path("ip", "arp")):
        interface = row.get("interface")
        if exclude:
            if interface in exclude:
                continue
        elif interface not in lan_interfaces:
            continue
        if not arp_is_present(row):
            continue
        ip = row.get("address")
        if not ip or ip in seen:
            continue
        seen.add(ip)
        devices.append(
            _device(ip, row.get("mac-address"), interface, lease_by_ip.get(ip) or {}, "arp", queues)
        )

    for ip, lease in lease_by_ip.items():
        if ip in seen or lease.get("status") != "bound" or lease.get("disabled"):
            continue
        age = lease.get("last_seen_seconds")
        if age is None or age > LEASE_ACTIVE_SECONDS:
            continue
        interface = server_interfaces.get(lease.get("server")) or "dhcp"
        if interface in exclude:
            continue
        seen.add(ip)
        devices.append(_device(ip, lease.get("mac_address"), interface, lease, "dhcp", queues))

    devices.sort(key=lambda d: ip_sort_key(d["ip"]))
    return devices


def traffic_total(api, interface):
    """One-shot live rate of the LAN-facing interface (a single sample, not an average)."""
    try:
        result = list(
            api.rawCmd("/interface/monitor-traffic", f"=interface={interface}", "=once=")
        )
    except Exception as exc:
        log.info("monitor-traffic unavailable: %s", type(exc).__name__)
        return None
    if not result:
        return None
    rx = leading_number(result[0].get("rx-bits-per-second"))
    tx = leading_number(result[0].get("tx-bits-per-second"))
    if rx is None and tx is None:
        return None
    return {
        "interface": interface,
        "method": "monitor_traffic_single_sample",
        "upload_bps": int(rx) if rx is not None else None,
        "download_bps": int(tx) if tx is not None else None,
    }