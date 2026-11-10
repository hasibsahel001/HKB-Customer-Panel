import ipaddress
from dataclasses import dataclass
from datetime import timedelta

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit
from app.auth.permissions import Permission, has_permission
from app.core.config import settings
from app.db import get_db
from app.models import User, UserSession, utcnow
from app.security import token_hash, tokens_equal

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_LOCAL_PROXY_HOSTS = {"127.0.0.1", "::1"}


@dataclass
class AuthContext:
    user: User
    session: UserSession


def client_ip(request: Request) -> str | None:
    """The caller's address.

    The Vite dev server proxies from this same machine, so the forwarded header is only
    trusted when the direct peer is local. The LAST entry is used because the trusted
    proxy appends it; earlier entries can be forged by the client.
    """
    peer = request.client.host if request.client else None
    if peer in _LOCAL_PROXY_HOSTS:
        forwarded = request.headers.get("x-forwarded-for", "")
        candidate = forwarded.split(",")[-1].strip()
        if candidate:
            try:
                ipaddress.ip_address(candidate)
                return candidate
            except ValueError:
                pass
    return peer


def _unauthorized(code="not_authenticated", message="Authentication required"):
    return HTTPException(status_code=401, detail={"code": code, "message": message})


def _authenticate(request: Request, db: Session, touch: bool) -> AuthContext:
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise _unauthorized()

    session = db.scalar(
        select(UserSession).where(UserSession.token_hash == token_hash(token))
    )
    if session is None:
        raise _unauthorized()

    now = utcnow()
    idle_deadline = session.last_seen_at + timedelta(minutes=settings.session_idle_minutes)
    if session.expires_at <= now or idle_deadline <= now:
        db.delete(session)
        db.commit()
        raise _unauthorized("session_expired", "The session has expired")

    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        db.delete(session)
        db.commit()
        raise _unauthorized()

    if touch:
        session.last_seen_at = now
        db.commit()
    return AuthContext(user=user, session=session)


def current_auth(request: Request, db: Session = Depends(get_db)) -> AuthContext:
    return _authenticate(request, db, touch=True)


def passive_auth(request: Request, db: Session = Depends(get_db)) -> AuthContext:
    """Like current_auth, but does not count as activity.

    The chat polls every few seconds; if that kept the session alive, the idle timeout would
    never apply to a tab that is just left open.
    """
    return _authenticate(request, db, touch=False)


def require_csrf(
    request: Request,
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    auth: AuthContext = Depends(current_auth),
) -> AuthContext:
    if request.method not in SAFE_METHODS:
        if not x_csrf_token or not tokens_equal(x_csrf_token, auth.session.csrf_token):
            raise HTTPException(
                status_code=403,
                detail={"code": "csrf_failed", "message": "Missing or invalid CSRF token"},
            )
    return auth


def require_permission(permission: Permission):
    def dependency(
        request: Request,
        auth: AuthContext = Depends(require_csrf),
        db: Session = Depends(get_db),
    ) -> AuthContext:
        if not has_permission(auth.user.role, permission):
            audit.record(
                db,
                "auth.permission_denied",
                user=auth.user,
                ip=client_ip(request),
                success=False,
                target=request.url.path,
                details={"permission": permission.value},
            )
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "forbidden",
                    "message": "You do not have permission to perform this action",
                },
            )
        return auth

    return dependency