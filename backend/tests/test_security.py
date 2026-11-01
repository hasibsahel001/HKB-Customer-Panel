import pytest

from app.api.customer import strip_debug
from app.auth.permissions import (
    Permission,
    Role,
    can_assign_role,
    can_manage_role,
    has_permission,
    permissions_for,
)
from app.auth.ratelimit import FailureLimiter
from app.core.config import settings
from app.core.errors import InvalidInput
from app.security import (
    hash_password,
    needs_rehash,
    token_hash,
    tokens_equal,
    validate_password,
    validate_username,
    verify_password,
)


@pytest.fixture(autouse=True)
def policy(monkeypatch):
    monkeypatch.setattr(settings, "password_min_length", 10)


def test_password_hash_roundtrip():
    hashed = hash_password("correct-horse-1")
    assert hashed != "correct-horse-1"
    assert verify_password(hashed, "correct-horse-1") is True
    assert verify_password(hashed, "wrong-password-1") is False
    assert verify_password("not-a-hash", "anything") is False
    assert needs_rehash(hashed) is False


def test_token_helpers():
    assert token_hash("abc") == token_hash("abc")
    assert token_hash("abc") != token_hash("abd")
    assert len(token_hash("abc")) == 64
    assert tokens_equal("same", "same") is True
    assert tokens_equal("same", "other") is False


@pytest.mark.parametrize("raw, expected", [("boss", "boss"), (" Boss.Agent_1 ", "boss.agent_1")])
def test_validate_username_accepts(raw, expected):
    assert validate_username(raw) == expected


@pytest.mark.parametrize("raw", ["ab", "has space", "x" * 33, "", "-start", "bad/char"])
def test_validate_username_rejects(raw):
    with pytest.raises(InvalidInput):
        validate_username(raw)


def test_validate_password():
    validate_password("correct-horse-1", "boss")
    with pytest.raises(InvalidInput):
        validate_password("short", "boss")
    with pytest.raises(InvalidInput):
        validate_password("a" * 129, "boss")
    with pytest.raises(InvalidInput):
        validate_password("administrator", "Administrator")


def test_permission_matrix():
    assert permissions_for(Role.SUPER_ADMIN) == set(Permission)
    assert has_permission("support_agent", Permission.CUSTOMER_CHECK)
    assert not has_permission("support_agent", Permission.USERS_MANAGE)
    assert not has_permission("support_agent", Permission.DEBUG_VIEW)
    assert has_permission("admin", Permission.DEBUG_VIEW)
    assert not has_permission("admin", Permission.AUDIT_VIEW)
    assert has_permission("read_only", Permission.CUSTOMER_CHECK)
    assert permissions_for("unknown_role") == set()


def test_role_management_rules():
    assert can_manage_role("super_admin", "admin")
    assert can_manage_role("super_admin", "super_admin")
    assert can_manage_role("admin", "support_agent")
    assert can_manage_role("admin", "read_only")
    assert not can_manage_role("admin", "admin")
    assert not can_manage_role("admin", "super_admin")
    assert not can_manage_role("support_agent", "read_only")
    assert not can_manage_role("bogus", "read_only")
    assert can_assign_role("admin", Role.SUPPORT_AGENT)
    assert not can_assign_role("admin", Role.ADMIN)


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_failure_limiter_window():
    clock = FakeClock()
    limiter = FailureLimiter(clock=clock)
    for _ in range(3):
        limiter.record("k")
    assert limiter.blocked("k", 3, 60) is True
    assert limiter.blocked("other", 3, 60) is False

    clock.now = 61.0
    assert limiter.blocked("k", 3, 60) is False

    limiter.record("k")
    limiter.reset("k")
    assert limiter.count("k", 60) == 0


def test_strip_debug_removes_technical_details():
    report = {
        "sections": {
            "temperature": {
                "ok": False,
                "error": "unavailable",
                "error_type": "RuntimeError",
                "error_detail": "temperature not supported",
                "data": None,
            },
            "queues": {
                "ok": True,
                "error_type": None,
                "error_detail": None,
                "data": {"skipped_reasons": ["ValueError: x"], "queues": []},
            },
        },
        "diagnostics": {
            "findings": [
                {"code": "section_unavailable", "evidence": {"section": "queues", "reason": "odd"}}
            ]
        },
    }
    result = strip_debug(report)
    assert "error_type" not in result["sections"]["temperature"]
    assert "error_detail" not in result["sections"]["temperature"]
    assert "skipped_reasons" not in result["sections"]["queues"]["data"]
    assert "reason" not in result["diagnostics"]["findings"][0]["evidence"]
    assert result["diagnostics"]["findings"][0]["evidence"]["section"] == "queues"