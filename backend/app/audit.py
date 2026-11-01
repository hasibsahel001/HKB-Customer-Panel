import json

from sqlalchemy.orm import Session

from app.models import AuditLog, User

_SENSITIVE_KEY_PARTS = ("password", "token", "secret", "credential", "csrf")


def _clean(details):
    if not details:
        return None
    safe = {
        key: value
        for key, value in details.items()
        if not any(part in key.lower() for part in _SENSITIVE_KEY_PARTS)
    }
    return json.dumps(safe, ensure_ascii=False, default=str)[:2000]


def record(
    db: Session,
    action: str,
    *,
    user: User | None = None,
    username: str | None = None,
    ip: str | None = None,
    success: bool = True,
    target: str | None = None,
    details: dict | None = None,
) -> None:
    name = user.username if user is not None else username
    entry = AuditLog(
        user_id=user.id if user is not None else None,
        username=name[:64] if name else None,
        action=action,
        target=target[:200] if target else None,
        ip=ip,
        success=success,
        details=_clean(details),
    )
    db.add(entry)
    db.commit()