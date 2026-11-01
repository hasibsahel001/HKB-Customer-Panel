import threading
import time
from collections import deque

_MAX_KEEP_SECONDS = 86_400


class FailureLimiter:
    """In-memory sliding-window counter. Correct for a single process only."""

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._events: dict[str, deque] = {}
        self._lock = threading.Lock()

    def _live_count(self, key: str, window_seconds: float) -> int:
        events = self._events.get(key)
        if not events:
            self._events.pop(key, None)
            return 0
        cutoff = self._clock() - window_seconds
        while events and events[0] <= cutoff:
            events.popleft()
        if not events:
            del self._events[key]
            return 0
        return len(events)

    def count(self, key: str, window_seconds: float) -> int:
        with self._lock:
            return self._live_count(key, window_seconds)

    def blocked(self, key: str, max_events: int, window_seconds: float) -> bool:
        return self.count(key, window_seconds) >= max_events

    def record(self, key: str) -> None:
        with self._lock:
            now = self._clock()
            events = self._events.setdefault(key, deque())
            events.append(now)
            while events and events[0] <= now - _MAX_KEEP_SECONDS:
                events.popleft()

    def reset(self, key: str) -> None:
        with self._lock:
            self._events.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._events.clear()


login_limiter = FailureLimiter()
check_limiter = FailureLimiter()


def reset_all() -> None:
    login_limiter.clear()
    check_limiter.clear()