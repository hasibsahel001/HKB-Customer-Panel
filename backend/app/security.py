import hashlib
import re
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import settings
from app.core.errors import InvalidInput

MAX_PASSWORD_LENGTH = 128

_hasher = PasswordHasher()
_DUMMY_HASH = _hasher.hash("timing-equalization-only")
_USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{2,31}$")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def burn_verify(password: str) -> None:
    """Spend the same time as a real check so unknown usernames are not distinguishable."""
    verify_password(_DUMMY_HASH, password)


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def tokens_equal(a: str, b: str) -> bool:
    return secrets.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def validate_username(raw: str) -> str:
    username = (raw or "").strip().lower()
    if not _USERNAME_RE.match(username):
        raise InvalidInput(
            "The username must be 3 to 32 characters: lowercase letters, digits, dot, dash or underscore"
        )
    return username


def validate_password(password: str, username: str) -> None:
    if len(password) < settings.password_min_length:
        raise InvalidInput(
            f"The password must be at least {settings.password_min_length} characters long"
        )
    if len(password) > MAX_PASSWORD_LENGTH:
        raise InvalidInput("The password is too long")
    if password.strip().lower() == (username or "").strip().lower():
        raise InvalidInput("The password must not be the same as the username")