import logging
import time
from concurrent.futures import ThreadPoolExecutor

from app.core.config import settings
from app.devices.customer_router import make_connector
from app.services.connectivity import classify_ping, summarize_ping
from app.services.diagnostics import diagnose_live
from app.services.snapshot import (
    close_quietly,
    ms_since,
    now_iso,
    open_extra,
    rows,
    run_section,
    valid_ip,
)
from app.services.vendors import lookup_vendor

log = logging.getLogger("hkb.live")


def _ping_host(api, host):
    try:
        data = list(
            api.rawCmd(
                "/ping",
                f"=address={host}",
                f"=count={settings.ping_count}",
                f"=interval={settings.ping_interval}",
            )
        )
        summary = summarize_ping(data)
        return {
            "host": host,
            "summary": summary,
            "reachable": summary["reachable"] if summary else None,
            "status": classify_ping(summary).value,
            "error": None,
        }
    except Exception as exc:
        log.info("ping failed: %s", type(exc).__name__)
        return {"host": host, "summary": None, "reachable": None, "status": "unknown", "error": type(exc).__name__}


def _ping(api, ctx):
    """Ping runs on the customer router. Reaching the router says nothing about the internet."""
    targets = []
    for raw in settings.ping_targets:
        host = valid_ip(raw)
        if host:
            targets.append(_ping_host(api, host))
    known = [t["reachable"] for t in targets if t["reachable"] is not None]
    return {
        "layers": {
            "router_connected": True,
            "pppoe_running": None,
            "gateway_reachable": None,
            "internet_reachable": any(known) if known else None,
        },
        "gateway": None,
        "targets": targets,
    }


def _ap_probe(api, ctx):
    """Ping the usual addresses of the customer's own access point, out of ether1."""
    peers = []
    for raw in settings.ap_probe_peers:
        host = valid_ip(raw)
        if not host:
            continue
        summary = None
        try:
            data = list(api.rawCmd("/ping", f"=address={host}", "=interface=ether1", "=count=1"))
            summary = summarize_ping(data)
        except Exception as exc:
            log.info("ap probe ping failed: %s", type(exc).__name__)
        peers.append(
            {
                "ip": host,
                "reachable": summary["reachable"] if summary else None,
                "avg_ms": summary["avg_ms"] if summary else None,
                "loss_percent": summary["loss_percent"] if summary else None,
                "mac": None,
                "vendor": None,
            }
        )

    if any(p["reachable"] for p in peers):
        arp = {r.get("address"): r for r in rows(api, "ip", "arp")}
        for peer in peers:
            if peer["reachable"]:
                mac = (arp.get(peer["ip"]) or {}).get("mac-address")
                peer["mac"] = mac
                peer["vendor"] = lookup_vendor(mac)
    return {"peers": peers, "found": [p["ip"] for p in peers if p["reachable"]]}


def _on_extra(conn, fn):
    api = open_extra(conn)
    if api is None:
        return None
    try:
        return run_section(fn, api, {})
    finally:
        close_quietly(api)


def collect_live(ip: str, tid: str, connector_cls=None) -> dict:
    """The slower measurements, run after the main snapshot has been shown."""
    started = time.perf_counter()
    conn = (connector_cls or make_connector)(ip, tid)
    conn.connect()
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            ap_future = pool.submit(_on_extra, conn, _ap_probe)
            ping_section = run_section(_ping, conn.api, {})
            ap_section = ap_future.result()
        if ap_section is None:  # the router refused an extra connection
            ap_section = run_section(_ap_probe, conn.api, {})

        ping_data = ping_section["data"] if ping_section["ok"] else None
        return {
            "fetched_at": now_iso(),
            "ping": ping_section,
            "ap_probe": ap_section,
            "diagnostics": diagnose_live(ping_data, None),
            "timings_ms": {"total": ms_since(started)},
        }
    finally:
        conn.close()