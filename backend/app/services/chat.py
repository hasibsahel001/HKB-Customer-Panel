"""Chat helpers: who is online, and checking pictures."""

import base64
import binascii
import threading
import time

from app.core.config import settings
from app.core.errors import InvalidInput


class Presence:
    """Panel users who polled the chat recently count as online (kept in memory, not in the database)."""

    def __init__(self):
        self._seen: dict[int, float] = {}
        self._lock = threading.Lock()

    def touch(self, user_id: int) -> None:
        with self._lock:
            self._seen[user_id] = time.monotonic()

    def online_ids(self) -> set:
        limit = time.monotonic() - settings.chat_online_seconds
        with self._lock:
            for user_id in [u for u, at in self._seen.items() if at < limit]:
                del self._seen[user_id]
            return set(self._seen)

    def clear(self) -> None:
        with self._lock:
            self._seen.clear()


PRESENCE = Presence()


def _mime_of(data: bytes):
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def parse_image(value: str):
    """Turns a data URL into (bytes, mime). The type comes from the bytes, never from the text."""
    text = value.strip()
    if not text.startswith("data:") or "," not in text:
        raise InvalidInput("The picture is not valid")
    payload = text.split(",", 1)[1]
    if len(payload) > settings.chat_max_image_bytes * 4 // 3 + 16:
        raise InvalidInput("The picture is too large")
    try:
        data = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError):
        raise InvalidInput("The picture is not valid")
    if not data or len(data) > settings.chat_max_image_bytes:
        raise InvalidInput("The picture is too large")
    mime = _mime_of(data)
    if mime is None:
        raise InvalidInput("Only PNG, JPEG, GIF and WebP pictures can be sent")
    return data, mime