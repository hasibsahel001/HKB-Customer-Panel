import logging
import socket
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import librouteros
from librouteros import exceptions as ros_exc

from app.core.config import settings
from app.core.errors import ConnectionFailed, FailureKind
from app.devices.base import DeviceConnector
from app.devices.credentials import Attempt, build_attempts
from app.devices.hints import HintCache
from app.devices.validation import validate_target_ip, validate_tid

log = logging.getLogger("hkb.connector")

GLOBAL_HINTS = HintCache(settings.connect_hint_ttl_seconds)

# Hints of fallback accounts do not depend on the Technical ID, so they are stored per IP only.
ANY_TID = "*"


@dataclass
class AttemptResult:
    account_index: int  # -1 means the TCP pre-check of a port
    port: int
    kind: FailureKind


def classify(exc: Exception) -> FailureKind:
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return FailureKind.TIMEOUT
    if isinstance(exc, ConnectionRefusedError):
        return FailureKind.PORT_CLOSED
    if isinstance(exc, (ros_exc.TrapError, ros_exc.FatalError)):
        msg = str(exc).lower()
        if "invalid user" in msg or "cannot log in" in msg or "login" in msg:
            return FailureKind.AUTH_REJECTED
        return FailureKind.PROTOCOL
    if isinstance(exc, OSError):
        return FailureKind.UNREACHABLE
    return FailureKind.PROTOCOL


def _check_port(ip: str, port: int, timeout: float):
    """None when the port accepts a TCP connection, otherwise the kind of failure."""
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return None
    except ConnectionRefusedError:
        return FailureKind.PORT_CLOSED
    except (socket.timeout, TimeoutError):
        return FailureKind.TIMEOUT
    except OSError:
        return FailureKind.UNREACHABLE


class PortProber:
    """Starts the TCP checks of all API ports at once and answers per port.

    state(port) only waits for that one port, so an open preferred port is never held up by a
    slow (filtered) one.
    """

    def __init__(self, ip: str, ports, timeout: float | None = None):
        wait = timeout or settings.probe_timeout
        ports = list(ports)
        self._pool = ThreadPoolExecutor(max_workers=max(1, len(ports)))
        self._futures = {port: self._pool.submit(_check_port, ip, port, wait) for port in ports}

    def state(self, port: int):
        return self._futures[port].result()

    def close(self) -> None:
        self._pool.shutdown(wait=False)


class _StaticProber:
    """Wraps a ready-made {port: failure or None} dict (used by tests)."""

    def __init__(self, states: dict):
        self._states = states

    def state(self, port: int):
        return self._states.get(port)

    def close(self) -> None:
        pass


def probe_ports(ip: str, ports, timeout: float | None = None) -> PortProber:
    return PortProber(ip, ports, timeout)


class CustomerRouterConnector(DeviceConnector):
    def __init__(self, ip: str, tid: str, connect_fn=librouteros.connect, probe_fn=None, hints=None):
        self.ip = validate_target_ip(ip)
        self.tid = validate_tid(tid)
        self._connect = connect_fn   # replaceable in tests
        self._probe = probe_fn       # None disables the TCP pre-check
        self._hints = hints          # None disables the account hint
        self.api = None
        self.used: Attempt | None = None
        self.failures: list[AttemptResult] = []
        self.login_attempts = 0

    def _hint(self):
        if self._hints is None:
            return None
        return self._hints.get(self.ip, self.tid) or self._hints.get(self.ip, ANY_TID)

    def _order(self, attempts):
        hint = self._hint()
        if hint is None:
            return attempts
        first = next((a for a in attempts if (a.account_index, a.port) == tuple(hint)), None)
        if first is None:
            return attempts
        return [first] + [a for a in attempts if a is not first]

    def _remember(self, attempt: Attempt) -> None:
        if self._hints is None:
            return
        key = self.tid if attempt.account_index == 0 else ANY_TID
        self._hints.put(self.ip, key, (attempt.account_index, attempt.port))

    def _forget(self) -> None:
        if self._hints is not None:
            self._hints.forget(self.ip, self.tid)
            self._hints.forget(self.ip, ANY_TID)

    def _start_probe(self, attempts):
        if self._probe is None:
            return None
        probe = self._probe(self.ip, sorted({a.port for a in attempts}))
        return probe if hasattr(probe, "state") else _StaticProber(probe)

    def connect(self):
        attempts = self._order(build_attempts(self.tid))
        prober = self._start_probe(attempts)
        bad_ports: set[int] = set()
        try:
            for att in attempts:
                if att.port in bad_ports:
                    continue
                if prober is not None:
                    kind = prober.state(att.port)
                    if kind is not None:
                        bad_ports.add(att.port)
                        self.failures.append(AttemptResult(-1, att.port, kind))
                        continue
                self.login_attempts += 1
                try:
                    self.api = self._connect(
                        host=self.ip,
                        username=att.username,
                        password=att.password,
                        port=att.port,
                        timeout=settings.connect_timeout,
                    )
                    self.used = att
                    self._remember(att)
                    log.info("connected %s via %r", self.ip, att)
                    return self
                except Exception as exc:
                    kind = classify(exc)
                    self.failures.append(AttemptResult(att.account_index, att.port, kind))
                    log.info("attempt failed %s %r: %s", self.ip, att, kind.value)
                    # A closed or silent port will not work with another account either.
                    if kind in (FailureKind.PORT_CLOSED, FailureKind.TIMEOUT):
                        bad_ports.add(att.port)

            self._forget()
            raise ConnectionFailed(self.failures)
        finally:
            if prober is not None:
                prober.close()

    def open_additional(self, timeout: float | None = None):
        """Open another API connection with the account that already worked."""
        if self.used is None:
            raise RuntimeError("not connected")
        return self._connect(
            host=self.ip,
            username=self.used.username,
            password=self.used.password,
            port=self.used.port,
            timeout=timeout or settings.connect_timeout,
        )

    def close(self):
        if self.api:
            self.api.close()
            self.api = None


def make_connector(ip: str, tid: str) -> CustomerRouterConnector:
    """The connector used by the application: TCP pre-check and account hint enabled."""
    return CustomerRouterConnector(
        ip,
        tid,
        probe_fn=probe_ports,
        hints=GLOBAL_HINTS if settings.connect_hint_enabled else None,
    )