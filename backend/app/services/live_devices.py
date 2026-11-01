"""Fast, repeated reads of the online devices of one customer router.

The dashboard asks for this about once a second. Logging in to a RouterOS device every second
would load weak routers, so one API connection per (IP, Technical ID) is kept open while the
panel keeps asking, shared by every browser tab, and closed after a short idle time.

Slow-changing data (DHCP servers, leases, queues) is cached for a few seconds; only the ARP table,
the LAN traffic sample and the wireless registration (signal, CCQ) are read on every call.
"""

import logging
import threading
import time
from datetime import datetime, timezone

from app.core.errors import ConnectionFailed, InvalidInput
from app.devices.customer_router import make_connector
from app.devices.validation import validate_target_ip, validate_tid
from app.services.analysis import classify_ccq, classify_chain, classify_signal, worst_status
from app.services.devices import collect_devices, lan_exclusions, traffic_total
from app.services.filtering import _infrastructure_ips
from app.services.network_parsing import parse_lease
from app.services.parsing import parse_registration, pick_wireless_interface, to_bool
from app.services.snapshot import _queue_list, rows

log = logging.getLogger("hkb.live_devices")

IDLE_SECONDS = 20.0        # close the connection when nobody has asked for this long
MIN_INTERVAL = 0.7         # several tabs asking at once share one reading
STATIC_REFRESH = 30.0      # DHCP servers, uplink interfaces
LEASE_REFRESH = 8.0
QUEUE_REFRESH = 10.0
MAX_ENTRIES = 60


class _Entry:
    def __init__(self):
        self.lock = threading.Lock()
        self.conn = None
        self.last_used = time.monotonic()
        self.last_result = None
        self.last_read = 0.0
        self.static_at = 0.0
        self.lease_at = 0.0
        self.queue_at = 0.0
        self.dhcp_interfaces: list = []
        self.wireless_name = None
        self.server_interfaces: dict = {}
        self.exclude: set = set()
        self.lease_by_ip: dict = {}
        self.queues = None

    def reset(self):
        """Forget the connection and every cache (used when the connection went stale)."""
        self.close()
        self.last_result = None
        self.last_read = 0.0
        self.static_at = self.lease_at = self.queue_at = 0.0

    def close(self):
        conn, self.conn = self.conn, None
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _read_static(api, entry: _Entry) -> None:
    try:
        servers = rows(api, "ip", "dhcp-server")
    except Exception as exc:
        log.info("dhcp servers unavailable: %s", type(exc).__name__)
        servers = []
    entry.dhcp_interfaces = sorted(
        {s.get("interface") for s in servers if s.get("interface") and not to_bool(s.get("disabled"))}
    )
    entry.server_interfaces = {
        s.get("name"): s.get("interface") for s in servers if s.get("name") and s.get("interface")
    }
    entry.exclude = lan_exclusions(api)
    try:
        picked = pick_wireless_interface(rows(api, "interface", "wireless"))
        entry.wireless_name = picked.get("name") if picked else None
    except Exception as exc:
        log.info("wireless interfaces unavailable: %s", type(exc).__name__)
        entry.wireless_name = None


def _wireless_analysis(reg) -> dict:
    """The same levels the full check computes, so the live numbers get the same colours."""
    signal = classify_signal(reg["signal_dbm"] if reg else None)
    tx = classify_ccq(reg["tx_ccq"] if reg else None)
    rx = classify_ccq(reg["rx_ccq"] if reg else None)
    ccq = worst_status(tx, rx)
    return {
        "signal": signal.value,
        "ccq": ccq.value,
        "overall": worst_status(signal, ccq).value,
        "ccq_tx": tx.value,
        "ccq_rx": rx.value,
        "chains": [
            {"chain": c["chain"], "level": classify_chain(c["tx_dbm"], c["rx_dbm"]).value}
            for c in (reg["chains"] if reg else [])
        ],
    }


def _read_wireless(api, entry: _Entry):
    """Signal, chains and CCQ of the customer's link. None when the router has no wireless."""
    name = entry.wireless_name
    if not name:
        return None
    try:
        raw = [r for r in rows(api, "interface", "wireless", "registration-table") if r.get("interface") == name]
    except Exception as exc:
        log.info("wireless registration unavailable: %s", type(exc).__name__)
        return None
    reg = parse_registration(raw[0]) if raw else None
    return {
        "interface": name,
        "registration_count": len(raw),
        "registration": reg,
        "analysis": _wireless_analysis(reg),
    }


def _read_leases(api, entry: _Entry) -> None:
    try:
        leases = [parse_lease(r) for r in rows(api, "ip", "dhcp-server", "lease")]
        entry.lease_by_ip = {lease["ip"]: lease for lease in leases if lease["ip"]}
    except Exception as exc:
        log.info("leases unavailable: %s", type(exc).__name__)
        entry.lease_by_ip = {}


def _read_queues(api, entry: _Entry) -> None:
    try:
        entry.queues = _queue_list(api, {})
    except Exception as exc:
        log.info("queues unavailable: %s", type(exc).__name__)
        entry.queues = None


class DeviceSessions:
    def __init__(self, connector_factory=None, clock=time.monotonic):
        self._factory = connector_factory
        self._clock = clock
        self._entries: dict = {}
        self._guard = threading.Lock()
        self._reaper_started = False

    # ------------------------------------------------------------------ public

    def read(self, ip: str, tid: str) -> dict:
        key = (validate_target_ip(ip), validate_tid(tid))
        entry = self._entry(key)
        with entry.lock:
            entry.last_used = self._clock()
            now = self._clock()
            if entry.last_result is not None and now - entry.last_read < MIN_INTERVAL:
                return entry.last_result
            try:
                result = self._read_locked(entry, key)
            except (ConnectionFailed, InvalidInput):
                raise
            except Exception as exc:
                # A kept connection can go stale (router rebooted, link flapped): reconnect once.
                log.info("device session reset for %s: %s", key[0], type(exc).__name__)
                entry.reset()
                result = self._read_locked(entry, key)
            entry.last_result = result
            entry.last_read = self._clock()
            entry.last_used = entry.last_read
            return result

    def reap(self) -> int:
        """Close connections nobody has used for a while. Returns how many were closed."""
        closed = 0
        now = self._clock()
        with self._guard:
            keys = list(self._entries)
        for key in keys:
            entry = self._entries.get(key)
            if entry is None or now - entry.last_used < IDLE_SECONDS:
                continue
            if not entry.lock.acquire(blocking=False):
                continue
            try:
                entry.close()
                with self._guard:
                    self._entries.pop(key, None)
                closed += 1
            finally:
                entry.lock.release()
        return closed

    def close_all(self) -> None:
        with self._guard:
            entries = list(self._entries.values())
            self._entries.clear()
        for entry in entries:
            with entry.lock:
                entry.close()

    # ----------------------------------------------------------------- internals

    def _entry(self, key) -> _Entry:
        with self._guard:
            entry = self._entries.get(key)
            if entry is None:
                if len(self._entries) >= MAX_ENTRIES:
                    oldest = min(self._entries, key=lambda k: self._entries[k].last_used)
                    stale = self._entries.pop(oldest)
                    if stale.lock.acquire(blocking=False):
                        try:
                            stale.close()
                        finally:
                            stale.lock.release()
                entry = self._entries[key] = _Entry()
            self._start_reaper()
            return entry

    def _start_reaper(self) -> None:
        if self._reaper_started:
            return
        self._reaper_started = True

        def loop():
            while True:
                time.sleep(5)
                try:
                    self.reap()
                except Exception as exc:  # the reaper must never die
                    log.warning("device session reaper failed: %s", type(exc).__name__)

        threading.Thread(target=loop, daemon=True, name="device-session-reaper").start()

    def _read_locked(self, entry: _Entry, key) -> dict:
        ip, tid = key
        if entry.conn is None:
            conn = (self._factory or make_connector)(ip, tid)
            conn.connect()
            entry.conn = conn
        api = entry.conn.api
        now = self._clock()

        if now - entry.static_at >= STATIC_REFRESH:
            _read_static(api, entry)
            entry.static_at = now
        if now - entry.lease_at >= LEASE_REFRESH:
            _read_leases(api, entry)
            entry.lease_at = now
        if now - entry.queue_at >= QUEUE_REFRESH:
            _read_queues(api, entry)
            entry.queue_at = now

        interfaces = entry.dhcp_interfaces or ["ether1"]
        devices = collect_devices(
            api,
            queues=entry.queues,
            lease_by_ip=entry.lease_by_ip,
            lan_interfaces=interfaces,
            server_interfaces=entry.server_interfaces,
            exclude=entry.exclude,
        )
        hidden = _infrastructure_ips()  # the customer's own access point is not a device
        devices = [d for d in devices if d["ip"] not in hidden]
        return {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "interfaces": interfaces,
            "count": len(devices),
            "total_traffic": traffic_total(api, interfaces[0]),
            "wireless": _read_wireless(api, entry),
            "devices": devices,
        }


DEVICE_SESSIONS = DeviceSessions()