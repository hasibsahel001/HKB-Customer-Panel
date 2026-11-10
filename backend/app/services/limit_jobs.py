"""Removes the temporary "Limit user" queues from the customer router after a delay.

The timer lives in the panel process. The router also gets a one-shot scheduler as a backup
(see router_actions.apply_limit_user), so the queues go away even if the panel is restarted.
"""

import logging
import threading
import time

from app import audit
from app.db import SessionLocal
from app.devices.customer_router import make_connector
from app.models import User
from app.services import router_actions as ra

log = logging.getLogger("hkb.limit_jobs")

RETRIES = 3
RETRY_WAIT_SECONDS = 20


class LimitTimers:
    def __init__(self):
        self._timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def schedule(self, key: str, delay: float, fn) -> None:
        """Starts the timer for `key`; a second press for the same router restarts the two minutes."""
        with self._lock:
            old = self._timers.pop(key, None)
            if old is not None:
                old.cancel()
            timer = threading.Timer(delay, self._run, args=(key, fn))
            timer.daemon = True
            self._timers[key] = timer
            timer.start()

    def cancel(self, key: str) -> None:
        with self._lock:
            old = self._timers.pop(key, None)
            if old is not None:
                old.cancel()

    def _run(self, key: str, fn) -> None:
        with self._lock:
            self._timers.pop(key, None)
        fn()


TIMERS = LimitTimers()


def _audit(user_id: int | None, target: str, success: bool, details: dict) -> None:
    db = SessionLocal()
    try:
        user = db.get(User, user_id) if user_id is not None else None
        audit.record(db, "router.limit_user_cleared", user=user, success=success, target=target, details=details)
    finally:
        db.close()


def make_clear_job(ip: str, tid: str, user_id: int | None, sleep=time.sleep):
    target = f"{ip}/{tid}"

    def run() -> None:
        last = "unknown"
        for attempt in range(RETRIES):
            try:
                conn = make_connector(ip, tid)
                conn.connect()
                try:
                    removed = ra.clear_limit_user(conn.api)
                finally:
                    conn.close()
                _audit(user_id, target, True, {"removed": removed})
                return
            except Exception as exc:  # the router may be unreachable for a moment
                last = type(exc).__name__
                log.info("clearing limit queues failed (%s), attempt %s", last, attempt + 1)
                if attempt < RETRIES - 1:
                    sleep(RETRY_WAIT_SECONDS)
        _audit(user_id, target, False, {"error": last})

    return run