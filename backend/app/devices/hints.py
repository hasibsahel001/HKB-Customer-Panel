import threading
import time


class HintCache:
    """Remembers which (account index, port) worked for an IP + Technical ID.

    Only indexes are stored, never credentials. Credentials are regenerated on every request.
    """

    def __init__(self, ttl_seconds: float, clock=time.monotonic):
        self._ttl = ttl_seconds
        self._clock = clock
        self._items: dict = {}
        self._lock = threading.Lock()

    def get(self, ip: str, tid: str):
        with self._lock:
            item = self._items.get((ip, tid))
            if item is None:
                return None
            value, expires = item
            if expires <= self._clock():
                del self._items[(ip, tid)]
                return None
            return value

    def put(self, ip: str, tid: str, value) -> None:
        with self._lock:
            if len(self._items) > 2000:
                self._items.clear()
            self._items[(ip, tid)] = (value, self._clock() + self._ttl)

    def forget(self, ip: str, tid: str) -> None:
        with self._lock:
            self._items.pop((ip, tid), None)