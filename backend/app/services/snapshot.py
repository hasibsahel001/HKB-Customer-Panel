import ipaddress
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from app.core.config import settings
from app.devices.customer_router import make_connector
from app.services.analysis import classify_ccq, classify_chain, classify_signal, worst_status
from app.services.devices import collect_devices, lan_exclusions
from app.services.devices import traffic_total as _traffic_total
from app.services.network_parsing import (
    parse_lease,
    parse_queue,
    queue_matches,
)
from app.services.parsing import (
    leading_number,
    parse_registration,
    pick_wireless_interface,
    to_bool,
)

log = logging.getLogger("hkb.snapshot")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ms_since(start: float) -> int:
    return round((time.perf_counter() - start) * 1000)


def rows(api, *path):
    return list(api.path(*path))


def valid_ip(value):
    try:
        return str(ipaddress.ip_address(str(value).strip()))
    except ValueError:
        return None


def open_extra(conn, timeout=None):
    """Another API connection for a parallel lane, or None when the router refuses it."""
    opener = getattr(conn, "open_additional", None)
    if opener is None:
        return None
    try:
        return opener(timeout)
    except Exception as exc:
        log.info("extra connection failed: %s", type(exc).__name__)
        return None


def close_quietly(api) -> None:
    try:
        api.close()
    except Exception:
        pass


def _interfaces(api, ctx):
    """The interface list is read once per lane and shared by its sections."""
    if "interfaces" not in ctx:
        ctx["interfaces"] = rows(api, "interface")
    return ctx["interfaces"]


def _identity(api, ctx):
    data = rows(api, "system", "identity")
    return {"identity": data[0].get("name") if data else None}


def _resource(api, ctx):
    r = rows(api, "system", "resource")[0]
    total = r.get("total-memory")
    free = r.get("free-memory")
    ram_pct = None
    if isinstance(total, int) and isinstance(free, int) and total > 0:
        ram_pct = round((total - free) * 100 / total, 1)

    cpu_load = r.get("cpu-load")
    # Opening several connections at once (parallel lanes) can cause a brief, misleading CPU
    # spike right at the moment this is read. If the first reading looks high, wait a moment
    # and read again; use the second (settled) value so a one-off spike doesn't become a false
    # "CPU high" finding. A genuinely sustained high load still shows up on the second read.
    if isinstance(cpu_load, (int, float)) and cpu_load >= settings.cpu_warning_percent:
        time.sleep(settings.cpu_recheck_delay_seconds)
        try:
            confirm = rows(api, "system", "resource")[0].get("cpu-load")
            if isinstance(confirm, (int, float)):
                cpu_load = confirm
        except Exception as exc:
            log.info("cpu recheck failed: %s", type(exc).__name__)

    return {
        "model": r.get("board-name"),
        "version": r.get("version"),
        "uptime": r.get("uptime"),
        "cpu_load": cpu_load,
        "ram_used_percent": ram_pct,
        "architecture": r.get("architecture-name"),
    }


def parse_temperature(data):
    """v6: [{'temperature': 45}]  |  v7: [{'name': 'temperature', 'value': '45'}]"""
    for row in data:
        if "temperature" in row:
            return leading_number(row["temperature"])
        if row.get("name") in ("temperature", "cpu-temperature", "board-temperature"):
            return leading_number(row.get("value"))
    return None


def _temperature(api, ctx):
    value = parse_temperature(rows(api, "system", "health"))
    if value is None:
        raise RuntimeError("temperature not supported")
    return {"temperature_c": value}


def _wireless(api, ctx):
    interface = pick_wireless_interface(rows(api, "interface", "wireless"))
    if interface is None:
        raise RuntimeError("no wireless interface")
    name = interface.get("name")

    raw_rows = [
        r
        for r in rows(api, "interface", "wireless", "registration-table")
        if r.get("interface") == name
    ]
    registrations = [parse_registration(r) for r in raw_rows]
    reg = registrations[0] if registrations else None

    ccq = None
    ccq_source = None
    if reg is not None:
        if reg["tx_ccq"] is not None:
            ccq, ccq_source = reg["tx_ccq"], "tx"
        elif reg["rx_ccq"] is not None:
            ccq, ccq_source = reg["rx_ccq"], "rx"

    signal_status = classify_signal(reg["signal_dbm"] if reg else None)
    tx_status = classify_ccq(reg["tx_ccq"] if reg else None)
    rx_status = classify_ccq(reg["rx_ccq"] if reg else None)
    ccq_status = worst_status(tx_status, rx_status)
    chain_levels = [
        {"chain": c["chain"], "level": classify_chain(c["tx_dbm"], c["rx_dbm"]).value}
        for c in (reg["chains"] if reg else [])
    ]

    return {
        "interface": name,
        "running": to_bool(interface.get("running")),
        "disabled": to_bool(interface.get("disabled")),
        "ssid": interface.get("ssid"),
        "frequency": interface.get("frequency"),
        "band": interface.get("band"),
        "channel_width": interface.get("channel-width"),
        "registration_count": len(registrations),
        "registration": reg,
        "ccq_used": ccq,
        "ccq_source": ccq_source,
        "analysis": {
            "signal": signal_status.value,
            "ccq": ccq_status.value,
            "overall": worst_status(signal_status, ccq_status).value,
            "ccq_tx": tx_status.value,
            "ccq_rx": rx_status.value,
            "chains": chain_levels,
        },
        "debug_registration_keys": sorted(raw_rows[0].keys()) if raw_rows else [],
    }


def _ether1(api, ctx):
    row = next((r for r in _interfaces(api, ctx) if r.get("name") == "ether1"), None)
    if row is None:
        raise RuntimeError("ether1 not found")

    data = {
        "name": "ether1",
        "running": to_bool(row.get("running")),
        "disabled": to_bool(row.get("disabled")),
        "rx_bytes_total": row.get("rx-byte"),
        "tx_bytes_total": row.get("tx-byte"),
        "link_downs": row.get("link-downs"),
        "last_link_up_time": row.get("last-link-up-time"),
        "link_rate": None,
        "full_duplex": None,
        "link_status": None,
        "addresses": None,
        "expected_addresses": [],
    }

    try:
        monitor = list(
            api.rawCmd("/interface/ethernet/monitor", "=numbers=ether1", "=once=")
        )
        if monitor:
            data["link_rate"] = monitor[0].get("rate")
            data["full_duplex"] = to_bool(monitor[0].get("full-duplex"))
            data["link_status"] = monitor[0].get("status")
    except Exception as exc:
        log.info("ether1 monitor unavailable: %s", type(exc).__name__)

    try:
        on_ether1 = [
            r.get("address") for r in rows(api, "ip", "address") if r.get("interface") == "ether1"
        ]
        data["addresses"] = on_ether1
        data["expected_addresses"] = [
            {"address": a, "configured": a in on_ether1} for a in settings.ap_expected_addresses
        ]
    except Exception as exc:
        log.info("address table unavailable: %s", type(exc).__name__)

    return data


def _dhcp(api, ctx):
    server_rows = rows(api, "ip", "dhcp-server")
    if not server_rows:
        raise RuntimeError("no dhcp server")

    interfaces = {r.get("name"): r for r in _interfaces(api, ctx)}

    bridge_ports = []
    if any(interfaces.get(s.get("interface"), {}).get("type") == "bridge" for s in server_rows):
        try:
            bridge_ports = rows(api, "interface", "bridge", "port")
        except Exception as exc:
            log.info("bridge ports unavailable: %s", type(exc).__name__)

    servers = []
    for s in server_rows:
        iface_name = s.get("interface")
        iface_type = interfaces.get(iface_name, {}).get("type")
        ports = []
        if iface_type == "bridge":
            ports = [p.get("interface") for p in bridge_ports if p.get("bridge") == iface_name]
        servers.append(
            {
                "name": s.get("name"),
                "interface": iface_name,
                "interface_type": iface_type,
                "bridge_ports": ports,
                "disabled": to_bool(s.get("disabled")),
                "address_pool": s.get("address-pool"),
                "lease_time": s.get("lease-time"),
            }
        )

    leases = [parse_lease(r) for r in rows(api, "ip", "dhcp-server", "lease")]
    ctx["lease_by_ip"] = {lease["ip"]: lease for lease in leases if lease["ip"]}
    ctx["dhcp_server_interfaces"] = {
        srv["name"]: srv["interface"] for srv in servers if srv["name"] and srv["interface"]
    }
    ctx["dhcp_interfaces"] = sorted(
        {s["interface"] for s in servers if s["interface"] and not s["disabled"]}
    )

    return {
        "servers": servers,
        "lease_count": len(leases),
        "bound_count": sum(1 for lease in leases if lease["status"] == "bound"),
        "conflict_count": sum(1 for lease in leases if lease["status"] == "conflict"),
    }


def _devices(api, ctx):
    """Devices online behind the router (see app.services.devices for the rules)."""
    interfaces = ctx.get("dhcp_interfaces") or ["ether1"]

    queues = None
    try:
        queues = _queue_list(api, ctx)
    except Exception as exc:
        log.info("queues unavailable for devices: %s: %s", type(exc).__name__, str(exc)[:200])

    devices = collect_devices(
        api,
        queues=queues,
        lease_by_ip=ctx.get("lease_by_ip", {}),
        lan_interfaces=interfaces,
        server_interfaces=ctx.get("dhcp_server_interfaces", {}),
        exclude=lan_exclusions(api),
    )
    ctx["device_ips"] = [d["ip"] for d in devices if d["ip"]]

    return {
        "interfaces": interfaces,
        "count": len(devices),
        "total_traffic": _traffic_total(api, interfaces[0]),
        "devices": devices,
    }


def _queue_list(api, ctx):
    """Read simple queues once per lane. A bad row is skipped and its reason recorded."""
    if "queues" not in ctx:
        queues = []
        reasons = []
        for row in rows(api, "queue", "simple"):
            try:
                queues.append(parse_queue(row, settings.queue_very_low_limit_bps))
            except Exception as exc:
                reason = f"{type(exc).__name__}: {str(exc)[:100]}"
                reasons.append(reason)
                log.info("queue row skipped: %s", reason)
        ctx["queues"] = queues
        ctx["queues_skipped_reasons"] = reasons
    return ctx["queues"]


def _queues(api, ctx):
    """Only queues tied to this customer by IP evidence (never by name)."""
    ips = [ctx["customer_ip"]] + ctx.get("device_ips", [])
    queues = _queue_list(api, ctx)
    matched = []
    for q in queues:
        hit = queue_matches(q["target"], ips)
        if hit:
            matched.append({**q, "matched_ips": hit})
    reasons = ctx.get("queues_skipped_reasons", [])
    return {
        "total_count": len(queues),
        "matched_count": len(matched),
        "unmatched_count": len(queues) - len(matched),
        "skipped_rows": len(reasons),
        "skipped_reasons": sorted(set(reasons))[:3],
        "queues": matched,
    }


def _pppoe(api, ctx):
    clients = rows(api, "interface", "pppoe-client")
    if not clients:
        raise RuntimeError("no pppoe client")

    enabled = [c for c in clients if not to_bool(c.get("disabled"))]
    client = (enabled or clients)[0]
    name = client.get("name")

    data = {
        "name": name,
        "username": client.get("user"),
        "client_count": len(clients),
        "running": to_bool(client.get("running")),
        "disabled": to_bool(client.get("disabled")),
        "underlying_interface": client.get("interface"),
        "service_name": client.get("service-name"),
        "status": None,
        "uptime": None,
        "local_address": None,
        "remote_address": None,
        "matches_panel_ip": None,
    }

    try:
        monitor = list(
            api.rawCmd("/interface/pppoe-client/monitor", f"=numbers={name}", "=once=")
        )
        if monitor:
            data["status"] = monitor[0].get("status")
            data["uptime"] = monitor[0].get("uptime")
            data["local_address"] = valid_ip(monitor[0].get("local-address"))
            data["remote_address"] = valid_ip(monitor[0].get("remote-address"))
    except Exception as exc:
        log.info("pppoe monitor unavailable: %s", type(exc).__name__)

    try:
        for row in rows(api, "ip", "address"):
            if row.get("interface") != name:
                continue
            local = valid_ip(str(row.get("address", "")).split("/")[0])
            peer = valid_ip(row.get("network"))
            if data["local_address"] is None:
                data["local_address"] = local
            if data["remote_address"] is None and peer and peer != local:
                data["remote_address"] = peer
            break
    except Exception as exc:
        log.info("address table unavailable: %s", type(exc).__name__)

    if data["local_address"]:
        data["matches_panel_ip"] = data["local_address"] == ctx["customer_ip"]
    return data


SECTIONS = {
    "identity": _identity,
    "resource": _resource,
    "temperature": _temperature,
    "wireless": _wireless,
    "ether1": _ether1,
    "dhcp": _dhcp,
    "devices": _devices,
    "queues": _queues,
    "pppoe": _pppoe,
}

LANES = [
    ["identity", "resource", "temperature", "ether1"],
    ["wireless", "pppoe"],
    ["dhcp", "devices", "queues"],
]


def run_section(fn, api, ctx):
    started = time.perf_counter()
    try:
        return {
            "ok": True,
            "data": fn(api, ctx),
            "error": None,
            "error_type": None,
            "error_detail": None,
            "fetched_at": now_iso(),
            "elapsed_ms": ms_since(started),
        }
    except Exception as exc:
        detail = str(exc)[:200]
        log.info("section failed: %s: %s: %s", fn.__name__, type(exc).__name__, detail)
        return {
            "ok": False,
            "data": None,
            "error": "unavailable",
            "error_type": type(exc).__name__,
            "error_detail": detail,
            "fetched_at": now_iso(),
            "elapsed_ms": ms_since(started),
        }


def _run_lane(api, names, customer_ip):
    ctx = {"customer_ip": customer_ip}
    return {name: run_section(SECTIONS[name], api, ctx) for name in names}


def _lane_on_extra(conn, names):
    api = open_extra(conn)
    if api is None:
        return names, None
    try:
        return names, _run_lane(api, names, conn.ip)
    finally:
        close_quietly(api)


def _collect(conn) -> dict:
    results: dict = {}
    leftovers = []
    if settings.parallel_connections:
        with ThreadPoolExecutor(max_workers=len(LANES)) as pool:
            first = pool.submit(_run_lane, conn.api, LANES[0], conn.ip)
            others = [pool.submit(_lane_on_extra, conn, names) for names in LANES[1:]]
            results.update(first.result())
            for future in others:
                names, data = future.result()
                if data is None:
                    leftovers.append(names)
                else:
                    results.update(data)
    else:
        results.update(_run_lane(conn.api, LANES[0], conn.ip))
        leftovers = list(LANES[1:])

    for names in leftovers:
        results.update(_run_lane(conn.api, names, conn.ip))
    return results


def collect_snapshot(ip: str, tid: str, connector_cls=None) -> dict:
    started = time.perf_counter()
    conn = (connector_cls or make_connector)(ip, tid)
    conn.connect()
    connect_ms = ms_since(started)
    try:
        results = _collect(conn)
        sections = {name: results[name] for name in SECTIONS if name in results}
        return {
            "ip": conn.ip,
            "technical_id": conn.tid,
            "connected_with_account": conn.used.account_index,
            "api_port": conn.used.port,
            "connect_attempts": getattr(conn, "login_attempts", 1),
            "fetched_at": now_iso(),
            "timings_ms": {
                "connect": connect_ms,
                "total": ms_since(started),
                "sections": {name: s["elapsed_ms"] for name, s in sections.items()},
            },
            "sections": sections,
        }
    finally:
        conn.close()